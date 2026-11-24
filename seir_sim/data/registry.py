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


# 신뢰 등급 (자료의 원출처와의 거리)
#   primary    : 원출처 기관이 직접 낸 자료 또는 그 공식 저장소
#   compiled   : 연구기관이 여러 공식 발표를 모아 정리한 자료 (JHU, OWID, OxCGRT, World Bank)
#   secondary  : 2차 집계 (예: Wikipedia 를 거친 자료) 또는 여러 출처 혼합
# 재배포: 원자료를 이 저장소에 넣지 않는다 (data_raw 는 git 제외). 파생 결과 공유 시 각 라이선스의 표시 의무를 따른다.
TIER = {
    "ne_admin0_10m": ("primary", "가능 (공개 도메인)"),
    "ne_admin1_10m": ("primary", "가능 (공개 도메인)"),
    "openflights": ("compiled", "가능 (ODbL: 출처 표시, 파생 DB 동일 조건)"),
    "wb_population": ("compiled", "가능 (CC BY 4.0: 출처 표시); 사본이라 원본 대조 필요"),
    "owid_covid": ("compiled", "가능 (CC BY 4.0)"),
    "jhu_csse_global": ("compiled", "가능 (CC BY 4.0)"),
    "oxcgrt_national": ("compiled", "가능 (CC BY 4.0)"),
    "gc19od_kr": ("secondary", "표시 의무; 이동 자료는 Google ToS, 시도 확진은 Wikimedia ToU"),
    "gc19od_countries": ("secondary", "표시 의무; 이동 자료는 Google ToS"),
    "worldpop_kor_2020_1km": ("primary", "가능 (CC BY 4.0)"),
    "gpw_v4_11": ("primary", "가능 (CC BY 4.0)"),
    "worldclim_tavg_vapr_10m": ("primary", "가능 (CC BY 4.0)"),
    "who_flunet": ("primary", "출처 표시 (WHO FluNet / GISRS); WHO 이용 약관 확인 필요"),
    "worldpop_kor_r2025a_1km": ("primary", "가능 (CC BY 4.0)"),
    "wb_population_api": ("compiled", "가능 (CC BY 4.0: 출처 표시)"),
    "era5_arco": ("primary", "출처 표시 (Copernicus licence); 재분석 모델 자료"),
    "admdongkor_sido": ("compiled", "가능 (SGIS 공공누리 1유형 출처표시 + 가공물 CC BY 4.0)"),
}


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
    # ------------------------------------------------------------------ 2단계: 감염병 자료
    Dataset("owid_covid", "epidemiology", "Our World in Data COVID-19 dataset (국가별 일별 확진·사망·검사·입원·백신)",
            ("https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv",
             "https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-codebook.csv",
             "https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/README.md"),
            "CC BY 4.0 (OWID); 하위 출처별 조건은 codebook 참조", "Our World in Data, 공식 GitHub 저장소 owid/covid-19-data",
            "master (파일의 마지막 날짜로 기록)", "국가", "2020-01 ~ 파일 마지막 날짜 (일별)",
            note="확진·사망의 원출처는 기간에 따라 JHU CSSE(2023-03 이전)와 WHO 이다 (codebook). OWID 자체 사이트(catalog.ourworldindata.org)는 이 환경에서 차단.",
            official_host="covid.ourworldindata.org / catalog.ourworldindata.org (차단)"),
    Dataset("jhu_csse_global", "epidemiology", "JHU CSSE COVID-19 global time series (확진·사망 누적)",
            ("https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_confirmed_global.csv",
             "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_deaths_global.csv"),
            "CC BY 4.0", "Johns Hopkins University CSSE, 공식 GitHub 저장소", "master (2023-03-10 수집 종료)",
            "국가 (일부 하위 지역)", "2020-01-22 ~ 2023-03-09 (일별 누적)",
            note="교차 검증용. 2023-03-10 에 수집이 끝났다."),
    Dataset("oxcgrt_national", "policy", "Oxford COVID-19 Government Response Tracker (국가별 일별 정책 지수)",
            ("https://raw.githubusercontent.com/OxCGRT/covid-policy-dataset/main/data/OxCGRT_compact_national_v1.csv",),
            "CC BY 4.0", "Blavatnik School of Government, University of Oxford, 공식 GitHub 저장소 OxCGRT/covid-policy-dataset",
            "main (v1)", "국가", "2020-01-01 ~ 2022-12-31 (일별)"),
    Dataset("gc19od_kr", "epidemiology", "Google COVID-19 Open Data v3: 대한민국 국가·시도별 통합 표 (확진·사망·인구·기상·이동·정책)",
            tuple(["https://storage.googleapis.com/covid19-open-data/v3/index.csv",
                   "https://storage.googleapis.com/covid19-open-data/v3/location/KR.csv",
                   "https://raw.githubusercontent.com/GoogleCloudPlatform/covid-19-open-data/main/README.md",
                   "https://raw.githubusercontent.com/GoogleCloudPlatform/covid-19-open-data/main/docs/table-epidemiology.md",
                   "https://raw.githubusercontent.com/GoogleCloudPlatform/covid-19-open-data/main/docs/table-demographics.md",
                   "https://raw.githubusercontent.com/GoogleCloudPlatform/covid-19-open-data/main/docs/table-weather.md",
                   "https://raw.githubusercontent.com/GoogleCloudPlatform/covid-19-open-data/main/docs/table-mobility.md",
                   "https://raw.githubusercontent.com/GoogleCloudPlatform/covid-19-open-data/main/docs/table-government-response.md"]
                  + [f"https://storage.googleapis.com/covid19-open-data/v3/location/KR_{c}.csv"
                     for c in (11, 26, 27, 28, 29, 30, 31, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50)]),
            "출력물 CC BY 4.0; 하위 출처별 조건 (시도 확진: Wikipedia 집계 [Wikimedia ToU], 기상: NOAA GHCN [미국 정부 공개], "
            "이동: Google Community Mobility [Google ToS], 인구: Wikidata [CC0] / WorldPop [CC BY 4.0])",
            "Google Cloud COVID-19 Open Data (storage.googleapis.com/covid19-open-data, 저장소 GoogleCloudPlatform/covid-19-open-data)",
            "v3 (2022-09 갱신 종료)", "국가, 시도 (17)", "2020-01-01 ~ 2022-09-17 (일별)",
            note="시도별 확진·사망은 2020-01-24 ~ 2020-09-09 만 있다 (원출처: 영문 Wikipedia 의 KCDC 브리핑 집계, 2차 자료). "
                 "기상은 지역 대표점 반경 300 km 안 가까운 NOAA 관측소 10곳의 평균이다."),
    Dataset("gc19od_countries", "epidemiology", "Google COVID-19 Open Data v3: 비교 국가 통합 표",
            tuple(f"https://storage.googleapis.com/covid19-open-data/v3/location/{c}.csv"
                  for c in ("JP", "NZ", "AU", "GB", "DE", "IT", "US", "BR", "IN", "ZA", "SE")),
            "출력물 CC BY 4.0; 하위 출처별 조건 (README 참조)", "Google Cloud COVID-19 Open Data v3",
            "v3 (2022-09 갱신 종료)", "국가", "2020-01-01 ~ 2022-09-17 (일별)",
            note="비교 국가는 지역·소득·정책이 다른 나라로 골랐다 (대한민국 과적합 방지)."),
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
            official_host="geodata.ucdavis.edu (2026-11 허용)",
            note="1970-2000 기후평년값이라 최신 기후가 아니다. 최신·기간별 기후는 era5_arco 를 쓴다."),
    Dataset("who_flunet", "epidemiology", "WHO FluNet: 국가별 주간 인플루엔자 실험실 검사 (검체 수, A/B 형별 양성 수)",
            ("https://xmart-api-public.who.int/FLUMART/VIW_FNT?$format=csv",),
            "WHO 이용 약관 (출처 표시: WHO FluNet, Global Influenza Surveillance and Response System)",
            "World Health Organization, FluNet (GISRS)", "받은 날의 최신판 (주간 갱신)", "국가 (일부 국가는 감시 체계별 행)",
            "1995 ~ 받은 날 직전 주 (ISO 주)", files=("VIW_FNT.csv",), official_host="xmart-api-public.who.int",
            note="실험실 검사 자료다: 양성 수는 검사 수와 감시 체계에 좌우되며 감염자 수가 아니다. ORIGIN_SOURCE 로 감시 체계(sentinel 등)를 구분한다."),
    Dataset("worldpop_kor_r2025a_1km", "population", "WorldPop Global 2015-2030 R2025A, 대한민국 1 km UN 총량 조정 (constrained)",
            tuple(f"https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/{y}/KOR/v1/1km_ua/constrained/kor_pop_{y}_CN_1km_R2025A_UA_v1.tif" for y in range(2015, 2031)),
            "CC BY 4.0", "WorldPop (University of Southampton)", "R2025A v1", "30 arc-sec (~1 km) 격자", "2015 ~ 2030 (연도별)",
            official_host="data.worldpop.org",
            note="모델 추정 인구 (인구조사·위성 자료 기반 재분배, UN 총량에 맞춤). 주민등록 인구가 아니다. 받은 날 이후 연도는 전망치다."),
    Dataset("wb_population_api", "population", "World Bank WDI 인구 (SP.POP.TOTL), 공식 API",
            ("https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=20000",),
            "CC BY 4.0", "World Bank, World Development Indicators", "API lastupdated 값 (파일에 기록)", "국가",
            "1960 ~ 최신 연도", files=("SP.POP.TOTL.json",), official_host="api.worldbank.org",
            note="wb_population (datahub 사본) 의 원출처. scripts/convert_wb_api.py 가 같은 열 형식의 population.csv 로 바꾼다."),
    Dataset("era5_arco", "climate", "ERA5 재분석 2 m 기온·이슬점 (Google ARCO-ERA5, 0.25°, 1시간)",
            (), "Copernicus licence (출처 표시)", "ECMWF ERA5 / Copernicus C3S (Google ARCO-ERA5 사본)",
            "Zarr v3 (속성 last_updated 기록)", "0.25°", "1940 ~ 확정판 마지막 날 (valid_time_stop)",
            official_host="storage.googleapis.com/gcp-public-data-arco-era5",
            note="원자료가 커서 내려받지 않고 seir_sim/data/era5.py 가 기간별 월 평균만 만든다 (data_processed/climate/). 관측 동화 모델 자료."),
    Dataset("admdongkor_sido", "boundaries", "대한민국 시도 경계 시계열 (통계청 SGIS 행정동 경계 기반, admdongkor light 판)",
            (), "SGIS 공공누리 제1유형 (출처표시) + 가공물 CC BY 4.0", "통계청 SGIS, 가공: github.com/vuski/admdongkor",
            "git 커밋 (manifest 에 기록)", "시도 (단순화 18.7%, EPSG:4326)", "1975 ~ 2026 (시점별 파일)",
            official_host="sgis.kostat.go.kr (원자료), github.com/vuski/admdongkor (가공)",
            note="scripts/fetch_admdongkor.py 가 받는다. Natural Earth 시도 경계의 광역시 면적 오류(광주 133 km² 등)를 대신한다."),
]}
