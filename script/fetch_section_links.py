from itertools import chain
from pathlib import Path
from typing import Literal, TypedDict
import json
import aiohttp

SECTION_LINKS_PATH = "artifact/section_links.json"
VD_INFO_PATH = "artifact/vd_info.json"
LINK_SHAPES_PATH = "public/highway_links.geojson"

# make sure folders exist
for path in [SECTION_LINKS_PATH, VD_INFO_PATH, LINK_SHAPES_PATH]:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


class FreewayLink(TypedDict):
    LinkID: str


class FreewaySection(TypedDict):
    SectionID: str
    LinkIDs: list[FreewayLink]
    SectionName: str
    RoadClass: int
    SectionLength: int
    SpeedLimit: int


async def fetch_section_info(session: aiohttp.ClientSession) -> list[FreewaySection]:
    async with session.get(
        "https://tdx.transportdata.tw/api/basic/v2/Road/Traffic/Section/Freeway",
        params={"$select": "SectionID,LinkIDs,SectionName", "$format": "JSON"},
    ) as resp:
        data = await resp.json()
        return data["Sections"]


class FreewayVDLink(FreewayLink):
    Bearing: str
    RoadDirection: str
    LaneNum: int
    ActualLaneNum: int


class FreewayVD(TypedDict):
    VDID: str
    DetectionLinks: list[FreewayVDLink]


async def fetch_VD_info(session: aiohttp.ClientSession) -> list[FreewayVD]:
    async with session.get(
        "https://tdx.transportdata.tw/api/basic/v2/Road/Traffic/VD/Freeway",
        params={"$select": "VDID,DetectionLinks", "$format": "JSON"},
    ) as resp:
        data = await resp.json()
        return data["VDs"]


class LinkShapeProperties(TypedDict):
    LinkID: str
    Version: str
    UpdateDate: str


class LinkShapeGeometry(TypedDict):
    type: Literal["LineString"]
    coordinates: list[tuple[float, float]]


class LinkShapeFeature(TypedDict):
    type: Literal["Feature"]
    properties: LinkShapeProperties
    geometry: LinkShapeGeometry


class LinkShapeCollection(TypedDict):
    type: Literal["FeatureCollection"]
    features: list[LinkShapeFeature]


async def fetch_link_shapes(session: aiohttp.ClientSession, link_ids: list[str]) -> LinkShapeCollection:
    async with session.post(
        "https://tdx.transportdata.tw/api/basic/v2/Road/Link/Shape/Geometry/GeoJson",
        json=link_ids,
    ) as resp:
        data = await resp.json()
        return data


async def main(client_id: str, client_secret: str):
    async with aiohttp.TCPConnector() as connector:
        async with aiohttp.ClientSession(connector=connector, connector_owner=False) as session:
            print("Get access token...")
            async with session.post(
                "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            ) as resp:
                data = await resp.json()
                access_token = data["access_token"]

            print(f"Access token obtained: {access_token[:5]}...{access_token[-5:]}")

        async with aiohttp.ClientSession(
            connector=connector,
            connector_owner=False,
            headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
        ) as session:
            print("Fetching section info...")
            section_links = await fetch_section_info(session)
            print(f"Section info fetched. Got {len(section_links)} sections.")
            with open(SECTION_LINKS_PATH, "w", encoding="utf-8") as f:
                json.dump(section_links, f, ensure_ascii=False, indent=2)
            print(f"Section info saved to {SECTION_LINKS_PATH}")

            vd_info = await fetch_VD_info(session)
            print(f"VD info fetched. Got {len(vd_info)} VDs.")
            with open(VD_INFO_PATH, "w", encoding="utf-8") as f:
                json.dump(vd_info, f, ensure_ascii=False, indent=2)
            print(f"VD info saved to {VD_INFO_PATH}")

            all_links = set(
                link["LinkID"]
                for link in chain(
                    *(section["LinkIDs"] for section in section_links if "LinkIDs" in section),
                    *(vd["DetectionLinks"] for vd in vd_info if "DetectionLinks" in vd),
                )
            )
            print(f"Total unique links to fetch shapes for: {len(all_links)}")

            print("Fetching link shapes...")
            link_shapes = await fetch_link_shapes(session, sorted(all_links))
            print(f"Link shapes fetched. Got {len(link_shapes['features'])} features.")

            print("Post-processing link shapes...")
            link_id_to_section_name = {
                link["LinkID"]: section["SectionName"]
                for section in section_links
                for link in section.get("LinkIDs", [])
            }
            cleared_link_shapes = {
                "type": link_shapes["type"],
                "features": [
                    {
                        "type": feature["type"],
                        "properties": {
                            "LinkID": feature["properties"]["LinkID"],
                            "SectionName": link_id_to_section_name.get(feature["properties"]["LinkID"], ""),
                        },
                        "geometry": feature["geometry"],
                    }
                    for feature in link_shapes["features"]
                ],
            }
            with open(LINK_SHAPES_PATH, "w", encoding="utf-8") as f:
                json.dump(cleared_link_shapes, f, ensure_ascii=False, separators=(",", ":"))
            print(f"Link shapes saved to {LINK_SHAPES_PATH}")


if __name__ == "__main__":
    import asyncio
    import os

    client_id = os.getenv("TDX_CLIENT_ID")
    client_secret = os.getenv("TDX_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError("Missing TDX_CLIENT_ID or TDX_CLIENT_SECRET environment variables")

    asyncio.run(main(client_id, client_secret))
