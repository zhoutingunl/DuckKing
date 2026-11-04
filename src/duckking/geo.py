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


def is_public_ip(ip: str | None) -> bool:
    if not ip:
        return False
    try:
        return ipaddress.ip_address(ip.strip()).is_global
    except ValueError:
        return False


def extract_client_ip(forwarded: str | None, client_host: str | None) -> str | None:
    """First X-Forwarded-For hop when present, else the socket peer address."""
    candidate = (forwarded or "").split(",")[0].strip() or client_host
    return candidate or None


def language_for(country_code: str | None) -> str:
    return "fr" if country_code in EUROPE_COUNTRY_CODES else "zh"


@dataclass
class RegionResult:
    language: str
    region: str | None
    room: str | None

    def public(self) -> dict:
        return {"language": self.language, "region": self.region, "room": self.room}


class RegionResolver:
    """Resolves the default UI language for a request. Fails closed to zh."""

    def __init__(
        self,
        db_dir: Path | None,
        country_header: str = "",
        french_room: str = "",
        lookup=None,
    ):
        self.db_dir = Path(db_dir).expanduser() if db_dir else None
        self.country_header = (country_header or "").strip()
        self.french_room = (french_room or "").strip()
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
        gateway = headers.get(self.country_header, "").strip() if self.country_header else ""
        if gateway:
            country = gateway.upper()
        else:
            ip = extract_client_ip(headers.get("x-forwarded-for"), client_ip)
            if is_public_ip(ip):
                try:
                    country = self._lookup(ip)
                except Exception as exc:  # any lookup failure means "unknown", never an error page
                    logger.debug("IP 属地查询异常: %s", type(exc).__name__)
                    country = None
        language = language_for(country)
        room = self.french_room or None if language == FRENCH_LANGUAGE else None
        return RegionResult(language=language, region=country or None, room=room)
