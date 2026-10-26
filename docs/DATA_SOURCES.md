# 외부 자료 출처 (scripts/fetch_data.py 가 생성)

원본 파일은 `data_raw/` 에 있고 git 에 넣지 않는다. 같은 파일인지는 SHA-256 으로 확인한다.

| id | 종류 | 상태 | 출처 | 라이선스 | 버전 | 해상도 | 기준 시점 | 용량 |
|---|---|---|---|---|---|---|---|---|
| ne_admin0_10m | boundaries | ok | Natural Earth, 공식 GitHub 저장소 nvkelso/natural-earth-vector | Public domain (Natural Earth terms of use) | 5.2.0-pre | 1:10m 벡터 | 경계: 버전 기준 (속성 POP_EST/POP_YEAR 포함) | 13.3 MB |
| ne_admin1_10m | boundaries | ok | Natural Earth, 공식 GitHub 저장소 nvkelso/natural-earth-vector | Public domain (Natural Earth terms of use) | 5.2.0-pre | 1:10m 벡터 | 경계: 버전 기준 | 40.7 MB |
| openflights | mobility | ok | OpenFlights.org, 공식 GitHub 저장소 jpatokal/openflights | Open Database License (ODbL) 1.0 | master | 공항 좌표, 항공사-공항 쌍 노선 (승객 수 없음) | 노선: 2014년 6월 기준 (OpenFlights 설명), 공항: 2017년 갱신 | 3.5 MB |
| wb_population | population | ok | World Bank WDI 의 datahub.io 사본 (GitHub datasets/population) | World Bank 자료 CC BY 4.0; datahub 패키지 ODC-PDDL | main | 국가 단위 | 1960 ~ 최신 연도 (파일에 기록) | 0.6 MB |
| worldpop_kor_2020_1km | population | blocked or failed | WorldPop (University of Southampton) | CC BY 4.0 | Global 2000-2020 1km UNadj | 30 arc-sec (~1km) 격자 | 2020 | 0.0 MB |
| gpw_v4_11 | population | unavailable: NASA Earthdata 로그인이 필요하고, 이 환경에서 sedac.ciesin.columbia.edu 가 차단됨. 사용자 승인에 따라 WorldPop 으로 대체. | NASA SEDAC / CIESIN | CC BY 4.0 | v4.11 | 30 arc-sec ~ 1 deg | 2000-2020 | 0.0 MB |
| worldclim_tavg_vapr_10m | climate | blocked or failed | WorldClim 2.1 (Fick & Hijmans 2017) | CC BY 4.0 | 2.1 | 10 arc-min | 1970-2000 기후평년 | 0.0 MB |

## 파일

### ne_admin0_10m: Natural Earth Admin 0 – Countries (1:10m)
- 공식 사이트: naciscdn.org (이 환경에서 차단)
- https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson → `data_raw/ne_admin0_10m/ne_10m_admin_0_countries.geojson` (13287234 bytes, sha256 `239eec57ac17f100…`, 2026-10-26T16:19:15+00:00)
- https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/VERSION → `data_raw/ne_admin0_10m/VERSION` (10 bytes, sha256 `fa43123c5e3a8022…`, 2026-10-26T16:19:15+00:00)

### ne_admin1_10m: Natural Earth Admin 1 – States, Provinces (1:10m)
- 공식 사이트: naciscdn.org (이 환경에서 차단)
- https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson → `data_raw/ne_admin1_10m/ne_10m_admin_1_states_provinces.geojson` (40726851 bytes, sha256 `22d0e3ad85eb3e27…`, 2026-10-26T16:19:17+00:00)
- https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/VERSION → `data_raw/ne_admin1_10m/VERSION` (10 bytes, sha256 `fa43123c5e3a8022…`, 2026-10-26T16:19:17+00:00)

### openflights: OpenFlights airports and routes
- 비고: 노선 수는 승객 수가 아니다. 이동률 omega 는 명시적 규모 가정으로만 만든다.
- https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat → `data_raw/openflights/airports.dat` (1127225 bytes, sha256 `9387cdb38df5bd66…`, 2026-10-26T16:11:59+00:00)
- https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat → `data_raw/openflights/routes.dat` (2377148 bytes, sha256 `bd373706238134f6…`, 2026-10-26T16:11:59+00:00)

### wb_population: World Bank population, total (SP.POP.TOTL), 국가별 연도별
- 비고: World Bank API 원본이 아니라 사본이다. 원본 대조는 api.worldbank.org 접근 허용 후 가능.
- 공식 사이트: api.worldbank.org
- https://raw.githubusercontent.com/datasets/population/main/data/population.csv → `data_raw/wb_population/population.csv` (556718 bytes, sha256 `2c697c3e668c8cb0…`, 2026-10-26T16:12:00+00:00)

### worldpop_kor_2020_1km: WorldPop 2020 1km UN-adjusted, Republic of Korea
- 공식 사이트: data.worldpop.org (이 환경에서 차단)
- https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/2020/KOR/kor_ppp_2020_1km_Aggregated_UNadj.tif → 실패: HTTP/1.1 403 Forbidden

### gpw_v4_11: GPW v4.11 population count
- 비고: NASA Earthdata 로그인이 필요하고, 이 환경에서 sedac.ciesin.columbia.edu 가 차단됨. 사용자 승인에 따라 WorldPop 으로 대체.
- 공식 사이트: sedac.ciesin.columbia.edu (차단)

### worldclim_tavg_vapr_10m: WorldClim 2.1 월평균 기온·수증기압 (10 arc-min)
- 공식 사이트: geodata.ucdavis.edu (이 환경에서 차단)
- https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_tavg.zip → 실패: HTTP/1.1 403 Forbidden
- https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_vapr.zip → 실패: HTTP/1.1 403 Forbidden

