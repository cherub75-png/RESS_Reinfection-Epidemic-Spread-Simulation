"""외부 자료 목록 (출처, 라이선스, 버전, 해상도, 기준 시점).

각 자료는 data_raw/<id>/ 아래에 내려받는다 (git 에 넣지 않음). 내려받은 결과는
data_raw/manifest.json 과 docs/DATA_SOURCES.md 에 기록한다 (scripts/fetch_data.py).

kind
  - boundaries   행정 경계 (지역 단위 i 를 정의)
  - population   인구 (지역 집계 또는 격자)
  - mobility     이동 (항공 노선 등)
  - climate      기후 격자
time_reference 는 자료가 나타내는 시점이다. 과거 보정용(historical)인지 최신 예측용(current)인지는
시나리오 설정의 DatasetRecord.role 로 정하며, 같은 자료를 두 용도로 섞지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Dataset:
    id: str
    kind: str
    title: str
    urls: tuple[str, ...]
    license: str
    source: str
    version: str
    resolution: str
    time_reference: str
    note: str = ""
    official_host: str = ""          # 공식 사이트 (차단 여부 기록용)
    files: tuple[str, ...] = field(default=())


NE_RAW = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master"

DATASETS: dict[str, Dataset] = {d.id: d for d in [
    Dataset("ne_admin0_10m", "boundaries", "Natural Earth Admin 0 – Countries (1:10m)",
            (f"{NE_RAW}/geojson/ne_10m_admin_0_countries.geojson", f"{NE_RAW}/VERSION"),
            "Public domain (Natural Earth terms of use)", "Natural Earth, 공식 GitHub 저장소 nvkelso/natural-earth-vector",
            "VERSION 파일 값으로 대체됨", "1:10m 벡터", "경계: 버전 기준 (속성 POP_EST/POP_YEAR 포함)",
            official_host="naciscdn.org (이 환경에서 차단)"),
    Dataset("ne_admin1_10m", "boundaries", "Natural Earth Admin 1 – States, Provinces (1:10m)",
            (f"{NE_RAW}/geojson/ne_10m_admin_1_states_provinces.geojson", f"{NE_RAW}/VERSION"),
            "Public domain (Natural Earth terms of use)", "Natural Earth, 공식 GitHub 저장소 nvkelso/natural-earth-vector",
            "VERSION 파일 값으로 대체됨", "1:10m 벡터", "경계: 버전 기준", official_host="naciscdn.org (이 환경에서 차단)"),
    Dataset("openflights", "mobility", "OpenFlights airports and routes",
            ("https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat",
             "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"),
            "Open Database License (ODbL) 1.0", "OpenFlights.org, 공식 GitHub 저장소 jpatokal/openflights",
            "master", "공항 좌표, 항공사-공항 쌍 노선 (승객 수 없음)",
            "노선: 2014년 6월 기준 (OpenFlights 설명), 공항: 2017년 갱신",
            note="노선 수는 승객 수가 아니다. 이동률 omega 는 명시적 규모 가정으로만 만든다."),
    Dataset("wb_population", "population", "World Bank population, total (SP.POP.TOTL), 국가별 연도별",
            ("https://raw.githubusercontent.com/datasets/population/main/data/population.csv",),
            "World Bank 자료 CC BY 4.0; datahub 패키지 ODC-PDDL", "World Bank WDI 의 datahub.io 사본 (GitHub datasets/population)",
            "main", "국가 단위", "1960 ~ 최신 연도 (파일에 기록)",
            note="World Bank API 원본이 아니라 사본이다. 원본 대조는 api.worldbank.org 접근 허용 후 가능.",
            official_host="api.worldbank.org"),
    Dataset("worldpop_kor_2020_1km", "population", "WorldPop 2020 1km UN-adjusted, Republic of Korea",
            ("https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/2020/KOR/kor_ppp_2020_1km_Aggregated_UNadj.tif",),
            "CC BY 4.0", "WorldPop (University of Southampton)", "Global 2000-2020 1km UNadj", "30 arc-sec (~1km) 격자",
            "2020", official_host="data.worldpop.org (이 환경에서 차단)"),
    Dataset("gpw_v4_11", "population", "GPW v4.11 population count", (),
            "CC BY 4.0", "NASA SEDAC / CIESIN", "v4.11", "30 arc-sec ~ 1 deg", "2000-2020",
            note="NASA Earthdata 로그인이 필요하고, 이 환경에서 sedac.ciesin.columbia.edu 가 차단됨. 사용자 승인에 따라 WorldPop 으로 대체.",
            official_host="sedac.ciesin.columbia.edu (차단)"),
    Dataset("worldclim_tavg_vapr_10m", "climate", "WorldClim 2.1 월평균 기온·수증기압 (10 arc-min)",
            ("https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_tavg.zip",
             "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_vapr.zip"),
            "CC BY 4.0", "WorldClim 2.1 (Fick & Hijmans 2017)", "2.1", "10 arc-min", "1970-2000 기후평년",
            official_host="geodata.ucdavis.edu (이 환경에서 차단)"),
]}
