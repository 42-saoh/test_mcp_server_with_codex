# PAT_SERVICE_LAYER_TX
Keywords: PAT_SERVICE_LAYER_TX transaction transactional service boundary uses_transaction
Summary: 트랜잭션 경계를 SQL 내부가 아니라 서비스 레이어(@Transactional)로 옮긴다.
Why: 트랜잭션 정책을 일관되게 관리하고 재사용/테스트 용이성 향상.
Do: @Transactional(propagation=..., isolation=..., readOnly=...)
Don't: 저장 프로시저 내부에서 begin/commit을 그대로 복제하지 않는다(가능하면).