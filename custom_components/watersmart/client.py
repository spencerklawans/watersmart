"""WaterSmart client to connect & scrape data."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import datetime as dt
from email import message_from_bytes
from email.message import Message
import functools
import imaplib
import re
from typing import Any, TypedDict, cast

import aiohttp
from bs4 import BeautifulSoup, PageElement

# Account number format will vary between municipality, so
# match on a string of non-whitespace characters.
ACCOUNT_NUMBER_RE = re.compile(r"^\S+$")
VERIFICATION_CODE_RE = re.compile(
    r"Enter this verification code to gain access:\s*(?P<code>\d{6})"
)


def _authenticated[F: Callable[..., Any], ReturnT](func: F) -> F:
    @functools.wraps(func)
    async def _pre_authenticate(
        self: WaterSmartClient,
        *args,  # noqa: ANN002
        **kwargs,  # noqa: ANN003
    ) -> ReturnT:
        await self._authenticate_if_needed()
        return cast("ReturnT", await func(self, *args, **kwargs))

    return cast("F", _pre_authenticate)


class AuthenticationError(Exception):
    """Authentication Error."""

    def __init__(self, errors: list[str] | None = None) -> None:
        """Initialize."""
        self._errors = errors


class InvalidAccountNumberError(Exception):
    """Invalid account number Error."""


class ScrapeError(Exception):
    """Scrape Error."""


class UsageHistoryPayload(TypedDict):
    """UsageHistoryPayload class."""

    data: UsageHistory


class UsageHistory(TypedDict):
    """UsageHistory class."""

    series: list[UsageRecord]


class UsageRecord(TypedDict):
    """UsageRecord class."""

    read_datetime: int
    gallons: float | None
    leak_gallons: int | None
    flags: None


class ImapConfig(TypedDict):
    """Configuration for accessing IMAP."""

    host: str
    username: str
    password: str
    port: int
    folder: str


class WaterSmartClient:
    """WaterSmart Client."""

    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession = None,
        imap_config: ImapConfig | None = None,
    ) -> None:
        """Initialize."""
        self._hostname = hostname
        self._username = username
        self._password = password
        self._session = session or aiohttp.ClientSession()
        self._account_number: str | None = None
        self._authenticated_at: dt.datetime | None = None
        self._imap_config = imap_config

    @_authenticated
    async def async_get_account_number(self) -> str | None:
        """Authenticate the client.

        Returns:
            The account number.
        """

        return self._account_number

    @_authenticated
    async def async_get_hourly_data(self) -> list[UsageRecord]:
        """Get hourly water usage data.

        Returns:
            The objects in the response data.
        """

        session = self._session
        hostname = self._hostname
        response = await session.get(
            f"https://{hostname}.watersmart.com/index.php/rest/v1/Chart/RealTimeChart"
        )
        response_json: UsageHistoryPayload = await response.json()

        return response_json["data"]["series"]

    async def _authenticate_if_needed(self) -> None:
        if not self._authenticated_at or self._authenticated_at < dt.datetime.now(
            tz=dt.UTC
        ) - dt.timedelta(minutes=10):
            await self._authenticate()
        self._authenticated_at = dt.datetime.now(tz=dt.UTC)

    async def _authenticate(self) -> None:
        session = self._session
        hostname = self._hostname
        login_response = await session.post(
            f"https://{hostname}.watersmart.com/index.php/welcome/login?forceEmail=1",
            data={
                "token": "",
                "email": self._username,
                "password": self._password,
            },
        )
        login_response_text = await login_response.text()
        soup = BeautifulSoup(login_response_text, "html.parser")

        login_refresh_token_node = soup.find("input", {"name": "loginRefreshToken"})
        login_refresh_token = (
            login_refresh_token_node.get("value", "")
            if login_refresh_token_node
            else None
        )

        if login_refresh_token:
            login_response = await session.post(
                f"https://{hostname}.watersmart.com/index.php/welcome/login?forceEmail=1",
                data={
                    "token": "",
                    "loginRefreshToken": login_refresh_token,
                    "email": self._username,
                    "password": self._password,
                },
            )
            login_response_text = await login_response.text()
            soup = BeautifulSoup(login_response_text, "html.parser")

        soup = await self._verify_if_needed(soup)

        errors = [error.text.strip() for error in soup.select(".error-message")]
        errors = [error for error in errors if error]

        if len(errors):
            raise AuthenticationError(errors)

        account = _assert_node(
            soup.find(id="account-navigation"), "Missing #account-navigation"
        )
        account_number_title = _assert_node(
            account.find(lambda node: node.get_text(strip=True) == "Account Number"),
            "Missing tag with string content `Account Number` under #account-navigation",
        )
        account_section = account_number_title.parent
        account_number_title.extract()

        account_number = account_section.text.strip()

        if not ACCOUNT_NUMBER_RE.match(account_number):
            self._account_number = None
            raise InvalidAccountNumberError("invalid account number: " + account_number)

        self._account_number = account_number

    async def _verify_if_needed(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Complete verification when required."""

        if not _requires_verification(soup):
            return soup

        verification_code = await self._get_verification_code()

        response = await self._session.post(
            f"https://{self._hostname}.watersmart.com/index.php/welcome/verify",
            data={"verificationCode": verification_code},
        )

        response_text = await response.text()
        return BeautifulSoup(response_text, "html.parser")

    async def _get_verification_code(self) -> str:
        """Retrieve the verification code from email."""

        if not self._imap_config:
            raise AuthenticationError(["verification required but IMAP is not configured"])

        await asyncio.sleep(30)
        return await asyncio.to_thread(self._fetch_code_from_imap)

    def _fetch_code_from_imap(self) -> str:
        """Fetch verification code from IMAP."""

        if not self._imap_config:
            raise AuthenticationError(["verification required but IMAP is not configured"])

        imap_config = self._imap_config
        imap = None

        try:
            imap = imaplib.IMAP4_SSL(imap_config["host"], imap_config["port"])
            imap.login(imap_config["username"], imap_config["password"])
            imap.select(imap_config["folder"])

            _, message_numbers = imap.search(None, 'SUBJECT "Verification"')
            if not message_numbers or not message_numbers[0]:
                raise AuthenticationError(["no verification email found"])

            latest_email_id = message_numbers[0].split()[-1]
            status, message_parts = imap.fetch(latest_email_id, "(RFC822)")

            if status != "OK" or not message_parts:
                raise AuthenticationError(["unable to fetch verification email"])

            email_body = message_parts[0][1]
            message = message_from_bytes(email_body)
            code = _extract_verification_code(message)
            if not code:
                raise AuthenticationError(["verification code not found in email"])

            return code
        finally:
            if imap is not None:
                try:
                    imap.logout()
                except Exception:  # noqa: BLE001
                    imap.close()


def _assert_node(node: PageElement, message: str) -> PageElement:
    if not node:
        raise ScrapeError(message)
    return node


def _requires_verification(soup: BeautifulSoup) -> bool:
    """Return True when the login response indicates verification is needed."""

    if soup.find("input", {"name": "verificationCode"}):
        return True

    verification_prompt = soup.find(
        string=lambda text: isinstance(text, str)
        and "verify your account" in text.lower()
    )

    return verification_prompt is not None


def _extract_verification_code(message: Message) -> str | None:
    """Extract verification code from an email message."""

    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue

        payload = part.get_payload(decode=True)
        if payload is None:
            continue

        try:
            body = payload.decode(part.get_content_charset() or "utf-8")
        except (LookupError, UnicodeDecodeError):
            continue

        if match := VERIFICATION_CODE_RE.search(body):
            return match.group("code")

    return None
