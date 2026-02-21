# DB Dependency Catalog

## linked_server
Keywords: linked_server PAT_ISOLATE_EXTERNAL_INTEGRATION openquery opendatasource external integration
Summary: Linked Server 호출은 “외부 시스템 의존성”으로 간주하고 격리해야 함.
Do: Adapter/Integration Layer로 분리하고, 호출 계약(타임아웃/리트라이/회로차단)을 문서화.
Testing: 계약 테스트 + 로컬 스텁(또는 테스트 더블) 기반으로 CI 안정화.
Related pattern: PAT_ISOLATE_EXTERNAL_INTEGRATION

## cross_db
Keywords: cross_db PAT_ISOLATE_EXTERNAL_INTEGRATION external integration three-part-name
Summary: Cross-DB 참조는 데이터 소유권/배포 단위/트랜잭션 경계를 깨뜨릴 수 있음.
Do: 조회 복제(read model), CDC/ETL, API 호출 등 대안 중 하나를 선택해 표준화.
Related pattern: PAT_ISOLATE_EXTERNAL_INTEGRATION