# 외부 자료 출처 (scripts/fetch_data.py 가 생성)

원본 파일은 `data_raw/` 에 있고 git 에 넣지 않는다. 같은 파일인지는 SHA-256 으로 확인한다.
품질 점검 결과: `docs/reports/2_data_quality.md`.

## 확보 현황 요약

| id | 종류 | 상태 | 신뢰 등급 | 재배포 |
|---|---|---|---|---|
| ne_admin0_10m | boundaries | 확보 | primary | 가능 (공개 도메인) |
| ne_admin1_10m | boundaries | 확보 | primary | 가능 (공개 도메인) |
| openflights | mobility | 확보 | compiled | 가능 (ODbL: 출처 표시, 파생 DB 동일 조건) |
| wb_population | population | 확보 | compiled | 가능 (CC BY 4.0: 출처 표시); 사본이라 원본 대조 필요 |
| worldpop_kor_2020_1km | population | 확보 | primary | 가능 (CC BY 4.0) |
| worldclim_tavg_vapr_10m | climate | 확보 | primary | 가능 (CC BY 4.0) |
| owid_covid | epidemiology | 확보 | compiled | 가능 (CC BY 4.0) |
| jhu_csse_global | epidemiology | 확보 | compiled | 가능 (CC BY 4.0) |
| oxcgrt_national | policy | 확보 | compiled | 가능 (CC BY 4.0) |
| gc19od_kr | epidemiology | 확보 | secondary | 표시 의무; 이동 자료는 Google ToS, 시도 확진은 Wikimedia ToU |
| gc19od_countries | epidemiology | 확보 | secondary | 표시 의무; 이동 자료는 Google ToS |
| who_flunet | epidemiology | 확보 | primary | 출처 표시 (WHO FluNet / GISRS); WHO 이용 약관 확인 필요 |
| worldpop_kor_r2025a_1km | population | 확보 | primary | 가능 (CC BY 4.0) |
| wb_population_api | population | 확보 | compiled | 가능 (CC BY 4.0: 출처 표시) |
| admdongkor_sido | boundaries | 확보 | compiled | 가능 (SGIS 공공누리 1유형 출처표시 + 가공물 CC BY 4.0) |
| gpw_v4_11 | population | 미확보: unavailable: NASA Earthdata 로그인이 필요하고, 이 환경에서 sedac.ciesin.columbia.edu 가 차단됨. 사용자 승인에 따라 WorldPop 으로 대체. | primary | 가능 (CC BY 4.0) |

신뢰 등급: primary = 원출처 기관 자료, compiled = 연구기관이 공식 발표를 모은 자료, secondary = 2차 집계 또는 여러 출처 혼합.

## 상세

| id | 종류 | 상태 | 출처 | 라이선스 | 버전 | 해상도 | 기준 시점 | 용량 |
|---|---|---|---|---|---|---|---|---|
| ne_admin0_10m | boundaries | ok | Natural Earth, 공식 GitHub 저장소 nvkelso/natural-earth-vector | Public domain (Natural Earth terms of use) | 5.2.0-pre | 1:10m 벡터 | 경계: 버전 기준 (속성 POP_EST/POP_YEAR 포함) | 13.3 MB |
| ne_admin1_10m | boundaries | ok | Natural Earth, 공식 GitHub 저장소 nvkelso/natural-earth-vector | Public domain (Natural Earth terms of use) | 5.2.0-pre | 1:10m 벡터 | 경계: 버전 기준 | 40.7 MB |
| openflights | mobility | ok | OpenFlights.org, 공식 GitHub 저장소 jpatokal/openflights | Open Database License (ODbL) 1.0 | master | 공항 좌표, 항공사-공항 쌍 노선 (승객 수 없음) | 노선: 2014년 6월 기준 (OpenFlights 설명), 공항: 2017년 갱신 | 3.5 MB |
| wb_population | population | ok | World Bank WDI 의 datahub.io 사본 (GitHub datasets/population) | World Bank 자료 CC BY 4.0; datahub 패키지 ODC-PDDL | main | 국가 단위 | 1960 ~ 최신 연도 (파일에 기록) | 0.6 MB |
| worldpop_kor_2020_1km | population | ok | WorldPop (University of Southampton) | CC BY 4.0 | Global 2000-2020 1km UNadj | 30 arc-sec (~1km) 격자 | 2020 | 0.7 MB |
| gpw_v4_11 | population | unavailable: NASA Earthdata 로그인이 필요하고, 이 환경에서 sedac.ciesin.columbia.edu 가 차단됨. 사용자 승인에 따라 WorldPop 으로 대체. | NASA SEDAC / CIESIN | CC BY 4.0 | v4.11 | 30 arc-sec ~ 1 deg | 2000-2020 | 0.0 MB |
| worldclim_tavg_vapr_10m | climate | ok | WorldClim 2.1 (Fick & Hijmans 2017) | CC BY 4.0 | 2.1 | 10 arc-min | 1970-2000 기후평년 | 64.6 MB |
| owid_covid | epidemiology | ok | Our World in Data, 공식 GitHub 저장소 owid/covid-19-data | CC BY 4.0 (OWID); 하위 출처별 조건은 codebook 참조 | master (파일의 마지막 날짜로 기록) | 국가 | 2020-01 ~ 파일 마지막 날짜 (일별) | 98.5 MB |
| jhu_csse_global | epidemiology | ok | Johns Hopkins University CSSE, 공식 GitHub 저장소 | CC BY 4.0 | master (2023-03-10 수집 종료) | 국가 (일부 하위 지역) | 2020-01-22 ~ 2023-03-09 (일별 누적) | 3.1 MB |
| oxcgrt_national | policy | ok | Blavatnik School of Government, University of Oxford, 공식 GitHub 저장소 OxCGRT/covid-policy-dataset | CC BY 4.0 | main (v1) | 국가 | 2020-01-01 ~ 2022-12-31 (일별) | 43.8 MB |
| gc19od_kr | epidemiology | ok | Google Cloud COVID-19 Open Data (storage.googleapis.com/covid19-open-data, 저장소 GoogleCloudPlatform/covid-19-open-data) | 출력물 CC BY 4.0; 하위 출처별 조건 (시도 확진: Wikipedia 집계 [Wikimedia ToU], 기상: NOAA GHCN [미국 정부 공개], 이동: Google Community Mobility [Google ToS], 인구: Wikidata [CC0] / WorldPop [CC BY 4.0]) | v3 (2022-09 갱신 종료) | 국가, 시도 (17) | 2020-01-01 ~ 2022-09-17 (일별) | 7.0 MB |
| gc19od_countries | epidemiology | ok | Google Cloud COVID-19 Open Data v3 | 출력물 CC BY 4.0; 하위 출처별 조건 (README 참조) | v3 (2022-09 갱신 종료) | 국가 | 2020-01-01 ~ 2022-09-17 (일별) | 15.4 MB |
| who_flunet | epidemiology | ok | World Health Organization, FluNet (GISRS) | WHO 이용 약관 (출처 표시: WHO FluNet, Global Influenza Surveillance and Response System) | 받은 날의 최신판 (주간 갱신) | 국가 (일부 국가는 감시 체계별 행) | 1995 ~ 받은 날 직전 주 (ISO 주) | 32.4 MB |
| worldpop_kor_r2025a_1km | population | ok | WorldPop (University of Southampton) | CC BY 4.0 | R2025A v1 | 30 arc-sec (~1 km) 격자 | 2015 ~ 2030 (연도별) | 11.6 MB |
| wb_population_api | population | ok | World Bank, World Development Indicators | CC BY 4.0 | API lastupdated 값 (파일에 기록) | 국가 | 1960 ~ 최신 연도 | 3.5 MB |
| admdongkor_sido | boundaries | ok | 통계청 SGIS, 가공: github.com/vuski/admdongkor | SGIS 공공누리 제1유형 (출처표시) + 가공물 CC BY 4.0 | git d5d5a821c8de (2026-10-17T19:36:02+09:00) | 시도 (단순화 18.7%, EPSG:4326) | 1975 ~ 2026 (시점별 파일) | 32.9 MB |

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
- https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/2020/KOR/kor_ppp_2020_1km_Aggregated_UNadj.tif → `data_raw/worldpop_kor_2020_1km/kor_ppp_2020_1km_Aggregated_UNadj.tif` (735034 bytes, sha256 `9c8b0d1609d7a1c0…`, 2026-11-09T05:46:50+00:00)

### gpw_v4_11: GPW v4.11 population count
- 비고: NASA Earthdata 로그인이 필요하고, 이 환경에서 sedac.ciesin.columbia.edu 가 차단됨. 사용자 승인에 따라 WorldPop 으로 대체.
- 공식 사이트: sedac.ciesin.columbia.edu (차단)

### worldclim_tavg_vapr_10m: WorldClim 2.1 월평균 기온·수증기압 (10 arc-min)
- 비고: 1970-2000 기후평년값이라 최신 기후가 아니다. 최신·기간별 기후는 era5_arco 를 쓴다.
- 공식 사이트: geodata.ucdavis.edu (2026-11 허용)
- https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_tavg.zip → `data_raw/worldclim_tavg_vapr_10m/wc2.1_10m_tavg.zip` (37364656 bytes, sha256 `5e567dcfe94379b9…`, 2026-11-09T05:46:51+00:00)
- https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_vapr.zip → `data_raw/worldclim_tavg_vapr_10m/wc2.1_10m_vapr.zip` (27215228 bytes, sha256 `0501b5b5cbbc6e2f…`, 2026-11-09T05:46:51+00:00)

### owid_covid: Our World in Data COVID-19 dataset (국가별 일별 확진·사망·검사·입원·백신)
- 비고: 확진·사망의 원출처는 기간에 따라 JHU CSSE(2023-03 이전)와 WHO 이다 (codebook). OWID 자체 사이트(catalog.ourworldindata.org)는 이 환경에서 차단.
- 공식 사이트: covid.ourworldindata.org / catalog.ourworldindata.org (차단)
- https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv → `data_raw/owid_covid/owid-covid-data.csv` (98391483 bytes, sha256 `8473d0f0fdf962e1…`, 2026-10-28T15:38:36+00:00)
- https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-codebook.csv → `data_raw/owid_covid/owid-covid-codebook.csv` (13763 bytes, sha256 `d7e681ccf6694c00…`, 2026-10-28T15:38:36+00:00)
- https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/README.md → `data_raw/owid_covid/README.md` (48239 bytes, sha256 `559086f3c7379f70…`, 2026-10-28T15:38:36+00:00)

### jhu_csse_global: JHU CSSE COVID-19 global time series (확진·사망 누적)
- 비고: 교차 검증용. 2023-03-10 에 수집이 끝났다.
- https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_confirmed_global.csv → `data_raw/jhu_csse_global/time_series_covid19_confirmed_global.csv` (1819904 bytes, sha256 `e6234a59eec4359d…`, 2026-10-28T15:38:42+00:00)
- https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_deaths_global.csv → `data_raw/jhu_csse_global/time_series_covid19_deaths_global.csv` (1255258 bytes, sha256 `4e87757a3e059c45…`, 2026-10-28T15:38:42+00:00)

### oxcgrt_national: Oxford COVID-19 Government Response Tracker (국가별 일별 정책 지수)
- https://raw.githubusercontent.com/OxCGRT/covid-policy-dataset/main/data/OxCGRT_compact_national_v1.csv → `data_raw/oxcgrt_national/OxCGRT_compact_national_v1.csv` (43837034 bytes, sha256 `fa5c95fa8f5e3865…`, 2026-10-28T15:38:42+00:00)

### gc19od_kr: Google COVID-19 Open Data v3: 대한민국 국가·시도별 통합 표 (확진·사망·인구·기상·이동·정책)
- 비고: 시도별 확진·사망은 2020-01-24 ~ 2020-09-09 만 있다 (원출처: 영문 Wikipedia 의 KCDC 브리핑 집계, 2차 자료). 기상은 지역 대표점 반경 300 km 안 가까운 NOAA 관측소 10곳의 평균이다.
- https://storage.googleapis.com/covid19-open-data/v3/index.csv → `data_raw/gc19od_kr/index.csv` (2426323 bytes, sha256 `2aa21339f5d9e4c3…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR.csv → `data_raw/gc19od_kr/KR.csv` (549512 bytes, sha256 `420dfacc96232e2b…`, 2026-10-28T15:38:44+00:00)
- https://raw.githubusercontent.com/GoogleCloudPlatform/covid-19-open-data/main/README.md → `data_raw/gc19od_kr/README.md` (22374 bytes, sha256 `63640ab50c5f89c3…`, 2026-10-28T15:38:44+00:00)
- https://raw.githubusercontent.com/GoogleCloudPlatform/covid-19-open-data/main/docs/table-epidemiology.md → `data_raw/gc19od_kr/table-epidemiology.md` (14861 bytes, sha256 `53d177ddc75e5409…`, 2026-10-28T15:38:44+00:00)
- https://raw.githubusercontent.com/GoogleCloudPlatform/covid-19-open-data/main/docs/table-demographics.md → `data_raw/gc19od_kr/table-demographics.md` (5247 bytes, sha256 `534e17627b835e07…`, 2026-10-28T15:38:44+00:00)
- https://raw.githubusercontent.com/GoogleCloudPlatform/covid-19-open-data/main/docs/table-weather.md → `data_raw/gc19od_kr/table-weather.md` (2139 bytes, sha256 `32a71c6d1501f751…`, 2026-10-28T15:38:44+00:00)
- https://raw.githubusercontent.com/GoogleCloudPlatform/covid-19-open-data/main/docs/table-mobility.md → `data_raw/gc19od_kr/table-mobility.md` (6825 bytes, sha256 `057aa6461000e79e…`, 2026-10-28T15:38:44+00:00)
- https://raw.githubusercontent.com/GoogleCloudPlatform/covid-19-open-data/main/docs/table-government-response.md → `data_raw/gc19od_kr/table-government-response.md` (3220 bytes, sha256 `9b6514cca99f7aec…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_11.csv → `data_raw/gc19od_kr/KR_11.csv` (263165 bytes, sha256 `4da6325f07f82f71…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_26.csv → `data_raw/gc19od_kr/KR_26.csv` (178991 bytes, sha256 `133bb6b5ffc2a4fb…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_27.csv → `data_raw/gc19od_kr/KR_27.csv` (263176 bytes, sha256 `c6afc2fd15388479…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_28.csv → `data_raw/gc19od_kr/KR_28.csv` (265188 bytes, sha256 `cdd00dc2dde00866…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_29.csv → `data_raw/gc19od_kr/KR_29.csv` (186381 bytes, sha256 `1447580f352bd00e…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_30.csv → `data_raw/gc19od_kr/KR_30.csv` (255837 bytes, sha256 `c229edffb9cd90e0…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_31.csv → `data_raw/gc19od_kr/KR_31.csv` (180495 bytes, sha256 `30997c25900e7be9…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_41.csv → `data_raw/gc19od_kr/KR_41.csv` (267842 bytes, sha256 `5eebd810f9cafb54…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_42.csv → `data_raw/gc19od_kr/KR_42.csv` (255986 bytes, sha256 `51efaac4791f696c…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_43.csv → `data_raw/gc19od_kr/KR_43.csv` (259543 bytes, sha256 `453ee724a743732b…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_44.csv → `data_raw/gc19od_kr/KR_44.csv` (256898 bytes, sha256 `fb942b0613efccae…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_45.csv → `data_raw/gc19od_kr/KR_45.csv` (257915 bytes, sha256 `4363b8b803934e65…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_46.csv → `data_raw/gc19od_kr/KR_46.csv` (255491 bytes, sha256 `960225f22c54ad1e…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_47.csv → `data_raw/gc19od_kr/KR_47.csv` (261856 bytes, sha256 `058189a730d7677e…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_48.csv → `data_raw/gc19od_kr/KR_48.csv` (265831 bytes, sha256 `4a86f5dce713218a…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_49.csv → `data_raw/gc19od_kr/KR_49.csv` (178475 bytes, sha256 `7eba8441f59fdbd1…`, 2026-10-28T15:38:44+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/KR_50.csv → `data_raw/gc19od_kr/KR_50.csv` (155250 bytes, sha256 `8caa5e72beb2619e…`, 2026-10-28T15:38:44+00:00)

### gc19od_countries: Google COVID-19 Open Data v3: 비교 국가 통합 표
- 비고: 비교 국가는 지역·소득·정책이 다른 나라로 골랐다 (대한민국 과적합 방지).
- https://storage.googleapis.com/covid19-open-data/v3/location/JP.csv → `data_raw/gc19od_countries/JP.csv` (569751 bytes, sha256 `55c80f949cbf3a82…`, 2026-10-28T15:38:53+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/NZ.csv → `data_raw/gc19od_countries/NZ.csv` (2399721 bytes, sha256 `7cd4870152a82c4b…`, 2026-10-28T15:38:53+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/AU.csv → `data_raw/gc19od_countries/AU.csv` (2612118 bytes, sha256 `c16a4764b69d3c2f…`, 2026-10-28T15:38:53+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/GB.csv → `data_raw/gc19od_countries/GB.csv` (2619780 bytes, sha256 `6abeaec9d087490b…`, 2026-10-28T15:38:53+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/DE.csv → `data_raw/gc19od_countries/DE.csv` (733701 bytes, sha256 `7e1270931db129b0…`, 2026-10-28T15:38:53+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/IT.csv → `data_raw/gc19od_countries/IT.csv` (552705 bytes, sha256 `7d4662b177fef0cc…`, 2026-10-28T15:38:53+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/US.csv → `data_raw/gc19od_countries/US.csv` (2907876 bytes, sha256 `e41081a81f285fe8…`, 2026-10-28T15:38:53+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/BR.csv → `data_raw/gc19od_countries/BR.csv` (1161344 bytes, sha256 `dbe1f907881a36b8…`, 2026-10-28T15:38:53+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/IN.csv → `data_raw/gc19od_countries/IN.csv` (767615 bytes, sha256 `5259ee75efb4295d…`, 2026-10-28T15:38:53+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/ZA.csv → `data_raw/gc19od_countries/ZA.csv` (548417 bytes, sha256 `477eee8fb6abdac5…`, 2026-10-28T15:38:53+00:00)
- https://storage.googleapis.com/covid19-open-data/v3/location/SE.csv → `data_raw/gc19od_countries/SE.csv` (507883 bytes, sha256 `f390105a94aa3380…`, 2026-10-28T15:38:53+00:00)

### who_flunet: WHO FluNet: 국가별 주간 인플루엔자 실험실 검사 (검체 수, A/B 형별 양성 수)
- 비고: 실험실 검사 자료다: 양성 수는 검사 수와 감시 체계에 좌우되며 감염자 수가 아니다. ORIGIN_SOURCE 로 감시 체계(sentinel 등)를 구분한다.
- 공식 사이트: xmart-api-public.who.int
- https://xmart-api-public.who.int/FLUMART/VIW_FNT?$format=csv → `data_raw/who_flunet/VIW_FNT.csv` (32386930 bytes, sha256 `62f800b506fcc7bd…`, 2026-11-09T05:46:14+00:00)

### worldpop_kor_r2025a_1km: WorldPop Global 2015-2030 R2025A, 대한민국 1 km UN 총량 조정 (constrained)
- 비고: 모델 추정 인구 (인구조사·위성 자료 기반 재분배, UN 총량에 맞춤). 주민등록 인구가 아니다. 받은 날 이후 연도는 전망치다.
- 공식 사이트: data.worldpop.org
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2015/KOR/v1/1km_ua/constrained/kor_pop_2015_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2015_CN_1km_R2025A_UA_v1.tif` (721140 bytes, sha256 `3ea087f5be9eb1ec…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2016/KOR/v1/1km_ua/constrained/kor_pop_2016_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2016_CN_1km_R2025A_UA_v1.tif` (721701 bytes, sha256 `067091f8bc6924cb…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2017/KOR/v1/1km_ua/constrained/kor_pop_2017_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2017_CN_1km_R2025A_UA_v1.tif` (722562 bytes, sha256 `706716e8843f2a0d…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2018/KOR/v1/1km_ua/constrained/kor_pop_2018_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2018_CN_1km_R2025A_UA_v1.tif` (722440 bytes, sha256 `e8692482da41ec2b…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2019/KOR/v1/1km_ua/constrained/kor_pop_2019_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2019_CN_1km_R2025A_UA_v1.tif` (723094 bytes, sha256 `75e73b4949960332…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2020/KOR/v1/1km_ua/constrained/kor_pop_2020_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2020_CN_1km_R2025A_UA_v1.tif` (723271 bytes, sha256 `f4167ca066ef6511…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2021/KOR/v1/1km_ua/constrained/kor_pop_2021_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2021_CN_1km_R2025A_UA_v1.tif` (723455 bytes, sha256 `3dffaa6d0f5492a6…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2022/KOR/v1/1km_ua/constrained/kor_pop_2022_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2022_CN_1km_R2025A_UA_v1.tif` (723263 bytes, sha256 `ce0ecb75769a4f4b…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2023/KOR/v1/1km_ua/constrained/kor_pop_2023_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2023_CN_1km_R2025A_UA_v1.tif` (723644 bytes, sha256 `f4523d9bf77814e1…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2024/KOR/v1/1km_ua/constrained/kor_pop_2024_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2024_CN_1km_R2025A_UA_v1.tif` (723281 bytes, sha256 `bf7dbc63ad585e8f…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2025/KOR/v1/1km_ua/constrained/kor_pop_2025_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2025_CN_1km_R2025A_UA_v1.tif` (723358 bytes, sha256 `0deaa0565663f0d5…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2026/KOR/v1/1km_ua/constrained/kor_pop_2026_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2026_CN_1km_R2025A_UA_v1.tif` (723241 bytes, sha256 `61d39aa6c91ab18c…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2027/KOR/v1/1km_ua/constrained/kor_pop_2027_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2027_CN_1km_R2025A_UA_v1.tif` (723326 bytes, sha256 `694364b2c8bee7a1…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2028/KOR/v1/1km_ua/constrained/kor_pop_2028_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2028_CN_1km_R2025A_UA_v1.tif` (723083 bytes, sha256 `5a68aeee4e6709ba…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2029/KOR/v1/1km_ua/constrained/kor_pop_2029_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2029_CN_1km_R2025A_UA_v1.tif` (722785 bytes, sha256 `84e70946dcd5a212…`, 2026-11-09T05:46:26+00:00)
- https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2030/KOR/v1/1km_ua/constrained/kor_pop_2030_CN_1km_R2025A_UA_v1.tif → `data_raw/worldpop_kor_r2025a_1km/kor_pop_2030_CN_1km_R2025A_UA_v1.tif` (722925 bytes, sha256 `6da526d19378b2db…`, 2026-11-09T05:46:26+00:00)

### wb_population_api: World Bank WDI 인구 (SP.POP.TOTL), 공식 API
- 비고: wb_population (datahub 사본) 의 원출처. scripts/convert_wb_api.py 가 같은 열 형식의 population.csv 로 바꾼다.
- 공식 사이트: api.worldbank.org
- https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=20000 → `data_raw/wb_population_api/SP.POP.TOTL.json` (3528198 bytes, sha256 `afebdcf7ed2ac0b3…`, 2026-11-09T05:46:50+00:00)

### admdongkor_sido: 대한민국 시도 경계 시계열 (통계청 SGIS 행정동 경계 기반, admdongkor light 판)
- 비고: scripts/fetch_admdongkor.py 가 받는다. Natural Earth 시도 경계의 광역시 면적 오류(광주 133 km² 등)를 대신한다.
- 공식 사이트: sgis.kostat.go.kr (원자료), github.com/vuski/admdongkor (가공)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_19751231_light.parquet → `data_raw/admdongkor_sido/sido_19751231_light.parquet` (889281 bytes, sha256 `8bf7c50b548fcab6…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_19801231_light.parquet → `data_raw/admdongkor_sido/sido_19801231_light.parquet` (900987 bytes, sha256 `e45d851333bcc507…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_19851231_light.parquet → `data_raw/admdongkor_sido/sido_19851231_light.parquet` (459577 bytes, sha256 `68a01aeb6e0f0700…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_19901231_light.parquet → `data_raw/admdongkor_sido/sido_19901231_light.parquet` (1002259 bytes, sha256 `13f7e210c6073760…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_19951231_light.parquet → `data_raw/admdongkor_sido/sido_19951231_light.parquet` (392381 bytes, sha256 `95644a967bc50b29…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20001231_light.parquet → `data_raw/admdongkor_sido/sido_20001231_light.parquet` (405142 bytes, sha256 `f87d0200b6d7d200…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20011231_light.parquet → `data_raw/admdongkor_sido/sido_20011231_light.parquet` (421913 bytes, sha256 `072289eed0ea5fca…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20021231_light.parquet → `data_raw/admdongkor_sido/sido_20021231_light.parquet` (377663 bytes, sha256 `e730116ba559972c…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20031231_light.parquet → `data_raw/admdongkor_sido/sido_20031231_light.parquet` (369540 bytes, sha256 `07c2c0a145bbe0d0…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20041231_light.parquet → `data_raw/admdongkor_sido/sido_20041231_light.parquet` (370538 bytes, sha256 `98ab2b121a7ff248…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20051231_light.parquet → `data_raw/admdongkor_sido/sido_20051231_light.parquet` (535771 bytes, sha256 `e93192f9e3a7791e…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20061231_light.parquet → `data_raw/admdongkor_sido/sido_20061231_light.parquet` (400207 bytes, sha256 `3fbce7b10cce2c4f…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20071231_light.parquet → `data_raw/admdongkor_sido/sido_20071231_light.parquet` (397894 bytes, sha256 `be87ae00934f0578…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20081231_light.parquet → `data_raw/admdongkor_sido/sido_20081231_light.parquet` (403465 bytes, sha256 `ee08038eed688217…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20091231_light.parquet → `data_raw/admdongkor_sido/sido_20091231_light.parquet` (396276 bytes, sha256 `5a2ee60ca7de13de…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20101231_light.parquet → `data_raw/admdongkor_sido/sido_20101231_light.parquet` (617543 bytes, sha256 `ac2179aac0aaaba2…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20111231_light.parquet → `data_raw/admdongkor_sido/sido_20111231_light.parquet` (896525 bytes, sha256 `2c9bef804bf39db6…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20121210_light.parquet → `data_raw/admdongkor_sido/sido_20121210_light.parquet` (498238 bytes, sha256 `a9d7a73f3ca65f98…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20121231_light.parquet → `data_raw/admdongkor_sido/sido_20121231_light.parquet` (546328 bytes, sha256 `fa36b74ad24c6221…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20131231_light.parquet → `data_raw/admdongkor_sido/sido_20131231_light.parquet` (457083 bytes, sha256 `1a9a6f155306bf21…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20141231_light.parquet → `data_raw/admdongkor_sido/sido_20141231_light.parquet` (472613 bytes, sha256 `ccd7abe48598ac2c…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20151231_light.parquet → `data_raw/admdongkor_sido/sido_20151231_light.parquet` (475866 bytes, sha256 `d2c24d044c12241d…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20160201_light.parquet → `data_raw/admdongkor_sido/sido_20160201_light.parquet` (508400 bytes, sha256 `ca32cb1141d3733a…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20170418_light.parquet → `data_raw/admdongkor_sido/sido_20170418_light.parquet` (500349 bytes, sha256 `0abb0a39a69e1933…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20170801_light.parquet → `data_raw/admdongkor_sido/sido_20170801_light.parquet` (500349 bytes, sha256 `15e9eab137a4e5d0…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20171016_light.parquet → `data_raw/admdongkor_sido/sido_20171016_light.parquet` (500864 bytes, sha256 `b9cbeceb2ceeb870…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20180301_light.parquet → `data_raw/admdongkor_sido/sido_20180301_light.parquet` (503261 bytes, sha256 `71d5f113dc2fd354…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20180401_light.parquet → `data_raw/admdongkor_sido/sido_20180401_light.parquet` (503261 bytes, sha256 `71d5f113dc2fd354…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20180724_light.parquet → `data_raw/admdongkor_sido/sido_20180724_light.parquet` (503261 bytes, sha256 `2057f7f03328a28d…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20181106_light.parquet → `data_raw/admdongkor_sido/sido_20181106_light.parquet` (500963 bytes, sha256 `2873fbcf76c9f1dc…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20190403_light.parquet → `data_raw/admdongkor_sido/sido_20190403_light.parquet` (499654 bytes, sha256 `844133da4f7fd559…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20190908_light.parquet → `data_raw/admdongkor_sido/sido_20190908_light.parquet` (500734 bytes, sha256 `96e92644f7ba840b…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20191001_light.parquet → `data_raw/admdongkor_sido/sido_20191001_light.parquet` (498773 bytes, sha256 `364bd9295694ac74…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20191231_light.parquet → `data_raw/admdongkor_sido/sido_20191231_light.parquet` (498825 bytes, sha256 `1505c0638463d681…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20200101_light.parquet → `data_raw/admdongkor_sido/sido_20200101_light.parquet` (501072 bytes, sha256 `16d15653333fdbd8…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20200701_light.parquet → `data_raw/admdongkor_sido/sido_20200701_light.parquet` (498541 bytes, sha256 `837ec82073521175…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20201001_light.parquet → `data_raw/admdongkor_sido/sido_20201001_light.parquet` (499052 bytes, sha256 `93f83dca93f55435…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20210101_light.parquet → `data_raw/admdongkor_sido/sido_20210101_light.parquet` (500659 bytes, sha256 `ebd295858a13d7d1…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20210401_light.parquet → `data_raw/admdongkor_sido/sido_20210401_light.parquet` (501111 bytes, sha256 `35678c2092c73393…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20210701_light.parquet → `data_raw/admdongkor_sido/sido_20210701_light.parquet` (501453 bytes, sha256 `b11ea01bf8ef4858…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20220101_light.parquet → `data_raw/admdongkor_sido/sido_20220101_light.parquet` (500059 bytes, sha256 `2406cf041bd48599…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20220309_light.parquet → `data_raw/admdongkor_sido/sido_20220309_light.parquet` (500059 bytes, sha256 `2406cf041bd48599…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20220401_light.parquet → `data_raw/admdongkor_sido/sido_20220401_light.parquet` (500059 bytes, sha256 `2406cf041bd48599…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20220701_light.parquet → `data_raw/admdongkor_sido/sido_20220701_light.parquet` (500388 bytes, sha256 `2ed1ac9b056f4a1d…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20221001_light.parquet → `data_raw/admdongkor_sido/sido_20221001_light.parquet` (499854 bytes, sha256 `6980448d06e636c8…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20230101_light.parquet → `data_raw/admdongkor_sido/sido_20230101_light.parquet` (499854 bytes, sha256 `6980448d06e636c8…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20230401_light.parquet → `data_raw/admdongkor_sido/sido_20230401_light.parquet` (500852 bytes, sha256 `95471400b19b34cf…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20230701_light.parquet → `data_raw/admdongkor_sido/sido_20230701_light.parquet` (509511 bytes, sha256 `5de0a5542bcaf34c…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20231001_light.parquet → `data_raw/admdongkor_sido/sido_20231001_light.parquet` (509605 bytes, sha256 `44a4a34026973adb…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20231231_light.parquet → `data_raw/admdongkor_sido/sido_20231231_light.parquet` (509589 bytes, sha256 `779564c3ff259de5…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20240101_light.parquet → `data_raw/admdongkor_sido/sido_20240101_light.parquet` (509676 bytes, sha256 `00ed10412293ba3e…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20240401_light.parquet → `data_raw/admdongkor_sido/sido_20240401_light.parquet` (512333 bytes, sha256 `33dd389f8953da74…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20240701_light.parquet → `data_raw/admdongkor_sido/sido_20240701_light.parquet` (512383 bytes, sha256 `f9f251f3a0701978…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20241001_light.parquet → `data_raw/admdongkor_sido/sido_20241001_light.parquet` (512383 bytes, sha256 `706ecd0bfeecb54e…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20241231_light.parquet → `data_raw/admdongkor_sido/sido_20241231_light.parquet` (512383 bytes, sha256 `706ecd0bfeecb54e…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20250101_light.parquet → `data_raw/admdongkor_sido/sido_20250101_light.parquet` (512367 bytes, sha256 `e7b5d1626062d462…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20250401_light.parquet → `data_raw/admdongkor_sido/sido_20250401_light.parquet` (512367 bytes, sha256 `e7b5d1626062d462…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20250701_light.parquet → `data_raw/admdongkor_sido/sido_20250701_light.parquet` (512367 bytes, sha256 `e7b5d1626062d462…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20251001_light.parquet → `data_raw/admdongkor_sido/sido_20251001_light.parquet` (512311 bytes, sha256 `e6e9a0481a8f7415…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20251231_light.parquet → `data_raw/admdongkor_sido/sido_20251231_light.parquet` (510745 bytes, sha256 `b1cd6542c0e76014…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20260201_light.parquet → `data_raw/admdongkor_sido/sido_20260201_light.parquet` (510261 bytes, sha256 `4d42046fd2334afb…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20260401_light.parquet → `data_raw/admdongkor_sido/sido_20260401_light.parquet` (510449 bytes, sha256 `b0d7466e84300da3…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20260701_light.parquet → `data_raw/admdongkor_sido/sido_20260701_light.parquet` (503357 bytes, sha256 `4948905c12ffaa9e…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/parquet/simplified/sido_20261001_light.parquet → `data_raw/admdongkor_sido/sido_20261001_light.parquet` (502502 bytes, sha256 `54f7dd2dd345946a…`, 2026-11-09T05:51:12+00:00)
- https://github.com/vuski/admdongkor/blob/d5d5a821c8de6cc337d47eeca604d7af76271c9b/LICENSE-DATA → `data_raw/admdongkor_sido/LICENSE-DATA` (2757 bytes, sha256 `d892791d5ba176e3…`, 2026-11-09T05:51:12+00:00)


## 파생 자료와 가정값 (손으로 관리: docs/data_sources_derived.md, fetch_data.py 가 이 절을 DATA_SOURCES.md 끝에 붙인다)

### 파생 자료 (이 저장소 코드가 원자료에서 만든 것)

| 파일 | 만드는 코드 | 입력 | 처리 | 등급 |
|---|---|---|---|---|
| `data_processed/tables/KOR_admin1_population_gc19od.csv` | `scripts/make_kor_admin1_tables.py` | gc19od_kr `KR_xx.csv` population 열 | 그대로 옮김 (시도 17개, 합 51,673,394) | secondary (원출처 미기록) |
| `data_processed/tables/KOR_admin1_climate_gc19od.csv` | 같은 스크립트 | gc19od_kr 기상 열 (NOAA GHCN-D 관측소 기반) | 달별 평균 (관측된 날만, 2020-01-01 ~ 2022-09 중순; 달마다 관측일 수 n_days 기록) | secondary, 기후평년값 아님 |
| `data_processed/KOR_admin1_gc19od.nc` (저장소 등록 이름 `KOR_admin1` v1) | `scripts/build_regions.py admin1 --population-table ... --climate-table ...` | NE admin1 경계, 위 두 표, OpenFlights | 측지 면적·중심, 균형 항공 ω, radiation 통근 C | 혼합 (아래 가정 포함) |
| `data_processed/world_countries_2019.nc` (등록 이름 `world_countries` v1) | `scripts/build_regions.py world --year 2019 ...` | NE admin0, World Bank 2019 (+ NE POP_EST), OpenFlights | 같은 처리 | 혼합 (아래 가정 포함) |
| `outputs/stage5/*` | `scripts/run_stage5_seir.py`, `scripts/report_stage5_forecast.py` | JHU, OxCGRT, Google 이동, OWID 백신·인구 | 시간순 예측 결과 (예측값이며 관측값 아님) | 모형 산출물 |
| `data_processed/tables/wb_population_api.csv` | `scripts/convert_wb_api.py` | wb_population_api (World Bank 공식 API, lastupdated 2026-10-08) | 열 형식만 바꿈 (값 그대로). datahub 사본과 겹치는 17,130개 (국가, 연도) 값이 모두 같음 (2026-11-09 확인) | compiled |
| `data_processed/climate/era5_<시작>_<끝>/` | `seir_sim/data/era5.py` (`python -m seir_sim data climate --start --end`) | ERA5 (Google ARCO-ERA5 Zarr v3) 2 m 기온·이슬점 | 매일 00·06·12·18 UTC 표본의 달력 월별 평균 (기온 °C, 수증기압 kPa = e_s(이슬점)); 확정 ERA5 범위만 | 재분석 (관측 동화 모델 자료) |
| `data_processed/variants/*.nc` | `seir_sim/data/periods.py` (`python -m seir_sim data variant`) | 경계 시점, 인구 연도, 기후 기간 선택 | 원본과 같은 이동 가정값으로 다시 만든 데이터셋 + 지역별 월 기후 (셀 중심 포함, cos 위도 가중; 셀보다 작은 지역은 대표점 셀) | 혼합 (선택한 자료에 따름) |
| 등록 이름 `KOR_admin1` v2 | `scripts/build_latest_datasets.py` | SGIS 시도 경계 2026-10-01 (16개 시도), WorldPop R2025A 2025, ERA5 2025-07 ~ 2026-06 | 위 변형본을 등록·활성화 | 혼합: 경계 compiled, 인구 모델 추정, 기후 재분석, 이동 가정 |
| 등록 이름 `world_countries` v2 | 같은 스크립트 | Natural Earth admin 0, World Bank 2025 (공식 API), ERA5 2025-07 ~ 2026-06 | 같은 처리 | 혼합 |

### 발견한 자료 문제: Natural Earth 1:10m 시도 경계 (2026-11-09)
- 대한민국 광역시의 면적이 실제보다 매우 작다: 광주 133 km² (실제 약 501), 부산 282 (약 770), 인천 367 (약 1,067), 대전 366 (약 539), 대구 466 (2020년 약 883). geoBoundaries 의 대한민국 시도도 같은 Natural Earth 경계다.
- 영향: (1) 인구 격자를 이 경계로 합산하면 광주가 52만 명으로 나온다 (실제 약 149만). (2) `KOR_admin1` v1 은 인구표(2차 자료)를 썼으므로 인구는 맞지만 인구밀도(인구 / 면적)가 광역시에서 2~4배 과대하다 → 밀도 함수 h(ρ) = (ρ/ρ_ref)^0.2 가 광역시에서 약 1.1~1.3배 크다. v1 로 만든 시도 단위 시나리오에 이 편향이 있다. 국가 단위 추정·예측 검증(3·5단계)은 단일 지역이라 영향이 없다.
- 조치: `KOR_admin1` v2 부터 통계청 SGIS 기반 경계(admdongkor)를 쓴다. WorldPop 2020 을 이 경계로 합산한 값과 2차 자료 인구표의 차이는 중앙 1.2%, 최대 세종 +14% (빠른 인구 증가로 기준 시점이 다른 것으로 보임), 인천 −6.6%.

등록된 데이터셋의 SHA-256·검증 결과·이전 버전과의 차이: `data_processed/datasets/registry.json` (`python -m seir_sim data list`).

### 가정값 (자료가 아님; 사용자가 바꿀 수 있음)

| 이름 | 값 | 쓰는 곳 | 근거·불확실성 |
|---|---|---|---|
| 국가 간 항공 이동 | 5e6 회/일 | 전 세계 데이터셋 `--air-trips-per-day` | 출처 확인한 승객 자료 없음. 크기 정도만 맞춘 가정 (불확실성 큼: 2배 이상) |
| 국가 간 통근 비율 | 0.002 | 전 세계 `--commute-fraction` | 가정. 국경 통근 자료 미확보 |
| 목적지 접촉 비율 | 0.3 | 전 세계·시도 `--contact-share` | 가정. 통근자 접촉 중 목적지에서 일어나는 비율 |
| 국내 항공 이동 (대한민국) | 9e4 회/일 | 시도 데이터셋 | 가정. 국내선 승객 통계(국토교통부 항공정보포털) 미확보 |
| 시도 간 통근 비율 (대한민국) | 0.05 | 시도 데이터셋 | 가정. 통계청 통근 자료(KOSIS) 차단으로 미확보 |
| 보고율 rho | 0.5 | 3·5단계 추정 | 식별 불가 (D-011) |
| R0_max | 6 | 3·5단계 추정 | u = 0 기준값, 상한 역할 (D-012) |
| 감염병 매개변수 (σ, γ, P, T, f, λ 등) | 1단계 COVID 유사 값 | 엔진·추정 | 코드 검증용 가정. 실제 COVID-19 추정치가 아님 |
| 국가 단위 이동 노선 구조 | OpenFlights 노선 (2014년 6월 기준) | 전 세계·시도 데이터셋 | 실제 자료이나 오래됨. 최신 공개 노선 자료는 확보하지 못함 (ICAO·OAG 는 유료) |

### 실제 관측값·추정값·예측값 구분
- 관측값: `data_raw/` 의 원자료와, 원자료를 그대로 옮긴 표 (위 표의 secondary 표 포함).
- 추정값: 3단계 u(t), I0, 지연, 과산포, k_f (보고서 3_calibration). 관측값으로 쓰지 않는다.
- 예측값: 5단계·최신 자료 예측. 검증에는 기점 뒤의 실제 관측값만 쓴다.
- 합성 자료: 테스트와 추정기 검증에만 쓰며 synthetic 표시가 붙는다.
