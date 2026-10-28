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
| owid_covid | epidemiology | 확보 | compiled | 가능 (CC BY 4.0) |
| jhu_csse_global | epidemiology | 확보 | compiled | 가능 (CC BY 4.0) |
| oxcgrt_national | policy | 확보 | compiled | 가능 (CC BY 4.0) |
| gc19od_kr | epidemiology | 확보 | secondary | 표시 의무; 이동 자료는 Google ToS, 시도 확진은 Wikimedia ToU |
| gc19od_countries | epidemiology | 확보 | secondary | 표시 의무; 이동 자료는 Google ToS |
| worldpop_kor_2020_1km | population | 미확보: blocked or failed | primary | 가능 (CC BY 4.0) |
| gpw_v4_11 | population | 미확보: unavailable: NASA Earthdata 로그인이 필요하고, 이 환경에서 sedac.ciesin.columbia.edu 가 차단됨. 사용자 승인에 따라 WorldPop 으로 대체. | primary | 가능 (CC BY 4.0) |
| worldclim_tavg_vapr_10m | climate | 미확보: blocked or failed | primary | 가능 (CC BY 4.0) |

신뢰 등급: primary = 원출처 기관 자료, compiled = 연구기관이 공식 발표를 모은 자료, secondary = 2차 집계 또는 여러 출처 혼합.

## 상세

| id | 종류 | 상태 | 출처 | 라이선스 | 버전 | 해상도 | 기준 시점 | 용량 |
|---|---|---|---|---|---|---|---|---|
| ne_admin0_10m | boundaries | ok | Natural Earth, 공식 GitHub 저장소 nvkelso/natural-earth-vector | Public domain (Natural Earth terms of use) | 5.2.0-pre | 1:10m 벡터 | 경계: 버전 기준 (속성 POP_EST/POP_YEAR 포함) | 13.3 MB |
| ne_admin1_10m | boundaries | ok | Natural Earth, 공식 GitHub 저장소 nvkelso/natural-earth-vector | Public domain (Natural Earth terms of use) | 5.2.0-pre | 1:10m 벡터 | 경계: 버전 기준 | 40.7 MB |
| openflights | mobility | ok | OpenFlights.org, 공식 GitHub 저장소 jpatokal/openflights | Open Database License (ODbL) 1.0 | master | 공항 좌표, 항공사-공항 쌍 노선 (승객 수 없음) | 노선: 2014년 6월 기준 (OpenFlights 설명), 공항: 2017년 갱신 | 3.5 MB |
| wb_population | population | ok | World Bank WDI 의 datahub.io 사본 (GitHub datasets/population) | World Bank 자료 CC BY 4.0; datahub 패키지 ODC-PDDL | main | 국가 단위 | 1960 ~ 최신 연도 (파일에 기록) | 0.6 MB |
| worldpop_kor_2020_1km | population | blocked or failed | WorldPop (University of Southampton) | CC BY 4.0 | Global 2000-2020 1km UNadj | 30 arc-sec (~1km) 격자 | 2020 | 0.0 MB |
| gpw_v4_11 | population | unavailable: NASA Earthdata 로그인이 필요하고, 이 환경에서 sedac.ciesin.columbia.edu 가 차단됨. 사용자 승인에 따라 WorldPop 으로 대체. | NASA SEDAC / CIESIN | CC BY 4.0 | v4.11 | 30 arc-sec ~ 1 deg | 2000-2020 | 0.0 MB |
| worldclim_tavg_vapr_10m | climate | blocked or failed | WorldClim 2.1 (Fick & Hijmans 2017) | CC BY 4.0 | 2.1 | 10 arc-min | 1970-2000 기후평년 | 0.0 MB |
| owid_covid | epidemiology | ok | Our World in Data, 공식 GitHub 저장소 owid/covid-19-data | CC BY 4.0 (OWID); 하위 출처별 조건은 codebook 참조 | master (파일의 마지막 날짜로 기록) | 국가 | 2020-01 ~ 파일 마지막 날짜 (일별) | 98.5 MB |
| jhu_csse_global | epidemiology | ok | Johns Hopkins University CSSE, 공식 GitHub 저장소 | CC BY 4.0 | master (2023-03-10 수집 종료) | 국가 (일부 하위 지역) | 2020-01-22 ~ 2023-03-09 (일별 누적) | 3.1 MB |
| oxcgrt_national | policy | ok | Blavatnik School of Government, University of Oxford, 공식 GitHub 저장소 OxCGRT/covid-policy-dataset | CC BY 4.0 | main (v1) | 국가 | 2020-01-01 ~ 2022-12-31 (일별) | 43.8 MB |
| gc19od_kr | epidemiology | ok | Google Cloud COVID-19 Open Data (storage.googleapis.com/covid19-open-data, 저장소 GoogleCloudPlatform/covid-19-open-data) | 출력물 CC BY 4.0; 하위 출처별 조건 (시도 확진: Wikipedia 집계 [Wikimedia ToU], 기상: NOAA GHCN [미국 정부 공개], 이동: Google Community Mobility [Google ToS], 인구: Wikidata [CC0] / WorldPop [CC BY 4.0]) | v3 (2022-09 갱신 종료) | 국가, 시도 (17) | 2020-01-01 ~ 2022-09-17 (일별) | 7.0 MB |
| gc19od_countries | epidemiology | ok | Google Cloud COVID-19 Open Data v3 | 출력물 CC BY 4.0; 하위 출처별 조건 (README 참조) | v3 (2022-09 갱신 종료) | 국가 | 2020-01-01 ~ 2022-09-17 (일별) | 15.4 MB |

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

