"""Visitor region to default UI language, resolved from a local ipdb database.

IP addresses never leave the machine: the neo.ipv4/ipv6.ipdb files are queried
in-process. Unknown, private or malformed addresses fall back to the default
Chinese UI instead of guessing. Raw IPs are neither logged nor returned.
"""

import ipaddress
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "zh"
FRENCH_LANGUAGE = "fr"

# “欧洲（非英国）”按地理欧洲取 ISO 316-1 alpha-2 国家码，仅排除英国（GB）。
# 含欧盟与 EEA、瑞士及地理欧洲的跨洲国家（TR/RU）、塞浦路斯和高加索三国；
# 不含哈萨克斯坦。北大西洋诸岛与皇家属地（JE/GG/IM/FO/SJ/AX）一并视为欧洲。
EUROPE_COUNTRY_CODES = frozenset(
    """AD AL AT AX BA BE BG BY CH CY CZ DE DK EE ES FI FO FR GG GI GR HR HU IE
    IM IS IT JE LI LT LU LV MC MD ME MK MT NL NO PL PT RO RS RU SE SI SJ SK SM
    TR UA VA XK""".split()
)

# 美国/英国默认英语（用户指定）；加拿大、澳大利亚等仍按未指定区域回退中文。
ENGLISH_COUNTRY_CODES = frozenset({"US", "GB"})


def is_public_ip(ip: str | None) -> bool:
    if not ip:
        return False
    try:
        return ipaddress.ip_address(ip.strip()).is_global
    except ValueError:
        return False


def is_trusted_proxy(client_host: str | None, trusted_proxies: tuple[str, ...]) -> bool:
    if not client_host:
        return False
    try:
        address = ipaddress.ip_address(client_host)
        return any(address in ipaddress.ip_network(cidr, strict=False) for cidr in trusted_proxies)
    except ValueError:
        return False


def extract_client_ip(
    forwarded: str | None,
    client_host: str | None,
    trusted_proxies: tuple[str, ...] = (),
) -> str | None:
    """Extract XFF only when the socket peer is in the configured proxy ranges."""
    if not is_trusted_proxy(client_host, trusted_proxies):
        return client_host if not forwarded else None
    hops = [hop.strip() for hop in (forwarded or "").split(",") if hop.strip()]
    return hops[-1] if hops else None


def language_for(country_code: str | None) -> str:
    if country_code in EUROPE_COUNTRY_CODES:
        return "fr"
    if country_code in ENGLISH_COUNTRY_CODES:
        return "en"
    return "zh"


@dataclass
class RegionResult:
    language: str
    region: str | None
    french_voice_available: bool
    english_voice_available: bool

    def public(self) -> dict:
        return {
            "language": self.language,
            "region": self.region,
            "french_voice_available": self.french_voice_available,
            "english_voice_available": self.english_voice_available,
        }


class RegionResolver:
    """Resolves the default UI language for a request. Fails closed to zh."""

    def __init__(
        self,
        db_dir: Path | None,
        country_header: str = "",
        french_rooms: tuple[str, ...] = (),
        english_rooms: tuple[str, ...] = (),
        trusted_proxies: tuple[str, ...] = ("127.0.0.1/32", "::1/128"),
        lookup=None,
    ):
        self.db_dir = Path(db_dir).expanduser() if db_dir else None
        self.country_header = (country_header or "").strip()
        self.french_rooms = tuple(french_rooms)
        self.english_rooms = tuple(english_rooms)
        self.trusted_proxies = tuple(trusted_proxies)
        self._lookup = lookup or self._lookup_ipdb
        self._dbs: dict[int, object] = {}

    def _open_city(self, version: int):
        from ipdb.city import City

        name = "neo.ipv4.ipdb" if version == 4 else "neo.ipv6.ipdb"
        return City(self.db_dir / name)

    def _lookup_ipdb(self, ip: str) -> str | None:
        if not self.db_dir:
            return None
        try:
            version = ipaddress.ip_address(ip).version
            db = self._dbs.get(version)
            if db is None:
                db = self._open_city(version)
                self._dbs[version] = db
            return db.find_info(ip, "CN").country_code or None
        except Exception as exc:  # missing files, malformed input, unknown IP
            logger.debug("IP 属地查询未命中: %s", type(exc).__name__)
            return None

    def resolve(self, headers, client_ip: str | None) -> RegionResult:
        country = None
        trusted_proxy = is_trusted_proxy(client_ip, self.trusted_proxies)
        gateway = (
            headers.get(self.country_header, "").strip()
            if trusted_proxy and self.country_header
            else ""
        )
        if gateway:
            country = gateway.upper()
        else:
            forwarded = headers.get("x-forwarded-for")
            # Never let a direct client choose another country's room by
            # forging XFF. If the socket peer is not a trusted proxy, use its
            # actual IP only when no forwarded header was supplied.
            if trusted_proxy:
                ip = extract_client_ip(forwarded, client_ip, self.trusted_proxies)
            else:
                has_forwarded_country = bool(
                    self.country_header and headers.get(self.country_header)
                )
                ip = None if forwarded or has_forwarded_country else client_ip
            if is_public_ip(ip):
                try:
                    country = self._lookup(ip)
                except Exception as exc:  # any lookup failure means "unknown", never an error page
                    logger.debug("IP 属地查询异常: %s", type(exc).__name__)
                    country = None
        language = language_for(country)
        return RegionResult(
            language=language,
            region=country or None,
            french_voice_available=bool(self.french_rooms),
            english_voice_available=bool(self.english_rooms),
        )
