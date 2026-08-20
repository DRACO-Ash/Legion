import httpx
import pytest
import respx

from src.udl_client import (
    ENDPOINT_ELSET,
    ENDPOINT_NOTIFICATION,
    UDLClient,
    UDLError,
    UDLNotConfigured,
)

BASE_URL = "https://unifieddatalibrary.test"


def notification_record(*satellites: dict) -> dict:
    return {
        "id": "rec-1",
        "classificationMarking": "U//DS-JCO-NOTIF",
        "dataMode": "REAL",
        "msgType": "JCO-HRR-SATELLITES",
        "source": "JCO",
        "msgBody": list(satellites),
    }


@pytest.fixture
def client():
    return UDLClient(
        base_url=BASE_URL, username="user", password="pass", timeout_seconds=2.0
    )


@pytest.fixture
def unconfigured_client():
    return UDLClient(
        base_url=BASE_URL, username=None, password=None, timeout_seconds=2.0
    )


@pytest.mark.anyio
async def test_fetch_jco_hrr_flattens_msgbody_across_records(client):
    payload = [
        notification_record(
            {"commonName": "COSMOS-2612", "satNo": "68762", "orbitRegime": "LEO"}
        ),
        notification_record(
            {"commonName": "COSMOS-2613", "satNo": "68763", "orbitRegime": "LEO"}
        ),
    ]
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(ENDPOINT_NOTIFICATION).mock(
            return_value=httpx.Response(200, json=payload)
        )
        satellites = await client.fetch_jco_hrr(window_hours=24)
    assert len(satellites) == 2
    assert satellites[0]["commonName"] == "COSMOS-2612"
    await client.aclose()


@pytest.mark.anyio
async def test_fetch_jco_hrr_sends_documented_query_params(client):
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get(ENDPOINT_NOTIFICATION).mock(
            return_value=httpx.Response(200, json=[])
        )
        await client.fetch_jco_hrr(window_hours=6)
    request = route.calls.last.request
    assert request.url.params["createdAt"] == ">now-6 hours"
    assert request.url.params["dataMode"] == "REAL"
    assert request.url.params["msgType"] == "JCO-HRR-SATELLITES"
    assert request.url.params["source"] == "JCO"
    await client.aclose()


@pytest.mark.anyio
async def test_fetch_jco_hrr_ignores_non_dict_msgbody_entries(client):
    payload = [notification_record({"commonName": "GOOD", "satNo": "1"}, "not-a-dict")]
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(ENDPOINT_NOTIFICATION).mock(
            return_value=httpx.Response(200, json=payload)
        )
        satellites = await client.fetch_jco_hrr()
    assert len(satellites) == 1
    await client.aclose()


@pytest.mark.anyio
async def test_fetch_jco_hrr_not_configured_raises_without_network_call(
    unconfigured_client,
):
    with pytest.raises(UDLNotConfigured):
        await unconfigured_client.fetch_jco_hrr()
    await unconfigured_client.aclose()


@pytest.mark.anyio
async def test_fetch_jco_hrr_unexpected_shape_raises_udl_error(client):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(ENDPOINT_NOTIFICATION).mock(
            return_value=httpx.Response(200, json={"not": "a list"})
        )
        with pytest.raises(UDLError):
            await client.fetch_jco_hrr()
    await client.aclose()


@pytest.mark.anyio
async def test_fetch_jco_hrr_http_error_raises_udl_error(client):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(ENDPOINT_NOTIFICATION).mock(return_value=httpx.Response(500))
        with pytest.raises(UDLError):
            await client.fetch_jco_hrr()
    await client.aclose()


@pytest.mark.anyio
async def test_fetch_jco_hrr_timeout_raises_udl_error(client):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(ENDPOINT_NOTIFICATION).mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        with pytest.raises(UDLError):
            await client.fetch_jco_hrr()
    await client.aclose()


@pytest.mark.anyio
async def test_fetch_jco_hrr_non_json_body_raises_udl_error(client):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(ENDPOINT_NOTIFICATION).mock(
            return_value=httpx.Response(200, text="not json")
        )
        with pytest.raises(UDLError):
            await client.fetch_jco_hrr()
    await client.aclose()


@pytest.mark.anyio
async def test_find_by_common_name_exact_case_insensitive_match(client):
    payload = [notification_record({"commonName": "Cosmos-2612", "satNo": "68762"})]
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(ENDPOINT_NOTIFICATION).mock(
            return_value=httpx.Response(200, json=payload)
        )
        found = await client.find_by_common_name("cosmos-2612")
    assert found["satNo"] == "68762"
    await client.aclose()


@pytest.mark.anyio
async def test_find_by_common_name_no_match_returns_none(client):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(ENDPOINT_NOTIFICATION).mock(return_value=httpx.Response(200, json=[]))
        found = await client.find_by_common_name("NOPE")
    assert found is None
    await client.aclose()


@pytest.mark.anyio
async def test_search_by_common_name_substring_match(client):
    payload = [
        notification_record(
            {"commonName": "COSMOS-2612", "satNo": "68762"},
            {"commonName": "COSMOS-2613", "satNo": "68763"},
        )
    ]
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(ENDPOINT_NOTIFICATION).mock(
            return_value=httpx.Response(200, json=payload)
        )
        results = await client.search_by_common_name("cosmos-261")
    assert len(results) == 2
    await client.aclose()


@pytest.mark.anyio
async def test_get_elset_returns_first_of_list(client):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(ENDPOINT_ELSET).mock(
            return_value=httpx.Response(
                200, json=[{"satNo": "68762", "inclination": 65.0}]
            )
        )
        elset = await client.get_elset("68762")
    assert elset["inclination"] == 65.0
    await client.aclose()


@pytest.mark.anyio
async def test_get_elset_returns_none_when_empty(client):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(ENDPOINT_ELSET).mock(return_value=httpx.Response(200, json=[]))
        elset = await client.get_elset("00000")
    assert elset is None
    await client.aclose()


@pytest.mark.anyio
async def test_get_elset_accepts_dict_payload(client):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(ENDPOINT_ELSET).mock(
            return_value=httpx.Response(
                200, json={"satNo": "68762", "inclination": 10.0}
            )
        )
        elset = await client.get_elset("68762")
    assert elset["inclination"] == 10.0
    await client.aclose()


@pytest.mark.anyio
async def test_get_elset_not_configured_raises(unconfigured_client):
    with pytest.raises(UDLNotConfigured):
        await unconfigured_client.get_elset("68762")
    await unconfigured_client.aclose()


@pytest.mark.anyio
async def test_get_elset_unexpected_shape_raises_udl_error(client):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get(ENDPOINT_ELSET).mock(
            return_value=httpx.Response(200, json="not a shape we handle")
        )
        with pytest.raises(UDLError):
            await client.get_elset("68762")
    await client.aclose()


@pytest.fixture
def anyio_backend():
    return "asyncio"
