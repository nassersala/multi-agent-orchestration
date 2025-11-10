# Event Sourcing + SSE Migration - TODO Checklist

**Project**: Multi-Agent Orchestration System Migration  
**Goal**: Replace PostgreSQL + WebSocket with SQLite Event Sourcing + SSE  
**Target**: 70% code reduction, simplified architecture  
**Timeline**: 4-6 weeks

---

## 📋 Phase 1: Foundation (Event Store Core)

### Step 1: SQLite Event Store - Append & Read All
- [x] Create `backend/event_store.py` with `EventStore` class
- [x] Implement `__init__` with SQLite table creation
- [x] Implement `append()` method with JSON serialization
- [x] Implement `get_all()` method with JSON parsing
- [x] Create `tests/test_event_store.py`
- [x] Write test: database and table creation
- [x] Write test: append event returns ID
- [x] Write test: append with all optional fields
- [x] Write test: retrieve all events
- [x] Write test: JSON round-trip serialization
- [x] Write test: timestamps populated correctly
- [x] **✅ Verify: All tests pass** (17/17 tests passing)

### Step 2: Event Store Queries
- [x] Add `since(event_id, limit)` method to `EventStore`
- [x] Add `by_aggregate(aggregate_id)` method
- [x] Add `by_type(event_type)` method
- [x] Write test: since returns events after ID
- [x] Write test: since with limit parameter
- [x] Write test: since with no new events
- [x] Write test: by_aggregate filters correctly
- [x] Write test: by_type filters correctly
- [x] **✅ Verify: All 10+ tests pass** (included in Step 1 - 17/17 passing)

### Step 3: Event Store Indexes & Performance
- [x] Add `_ensure_indexes()` private method (integrated into `_init_db`)
- [x] Create index on `(aggregate_id, aggregate_type)`
- [x] Create index on `type`
- [x] Create index on `timestamp DESC`
- [ ] Create `tests/test_event_store_performance.py`
- [ ] Write test: append performance <1ms
- [ ] Write test: query performance <10ms for 1000 events
- [ ] Write test: since performance <10ms
- [ ] **✅ Verify: Performance targets met**

**Note**: Steps 1-2 and indexes from Step 3 completed together. Thread-safety tests included.

---

## 📋 Phase 2: State Management (Pure Functions)

### Step 4: Event Type Definitions & Base State Model
- [ ] Create `backend/event_types.py` with event constants
- [ ] Define `ORCHESTRATOR_INITIALIZED` constant
- [ ] Define `AGENT_CREATED` constant
- [ ] Define `AGENT_COMMANDED` constant
- [ ] Define `COST_INCURRED` constant
- [ ] Define all other event type constants (15+ total)
- [ ] Create `backend/models.py`
- [ ] Define `Agent` dataclass (frozen=True)
- [ ] Define `ChatMessage` dataclass (frozen=True)
- [ ] Define `OrchestratorState` dataclass (frozen=True)
- [ ] Create `tests/test_models.py`
- [ ] Write test: dataclasses are immutable
- [ ] Write test: default values work
- [ ] Write test: can create with all fields
- [ ] **✅ Verify: Models are immutable and well-typed**

### Step 5: State Projection Functions
- [ ] Create `backend/projections.py`
- [ ] Implement `apply_event(state, event)` function
- [ ] Handle `ORCHESTRATOR_INITIALIZED` event
- [ ] Handle `AGENT_CREATED` event
- [ ] Handle `AGENT_STATUS_CHANGED` event
- [ ] Handle `COST_INCURRED` event
- [ ] Handle `USER_MESSAGE_RECEIVED` event
- [ ] Handle `ORCHESTRATOR_RESPONSE_GENERATED` event
- [ ] Handle `AGENT_DELETED` event
- [ ] Handle unknown event types (return unchanged)
- [ ] Implement `rebuild_state(events)` function
- [ ] Create `tests/test_projections.py`
- [ ] Write test for each event type (8+ tests)
- [ ] Write test: unknown event returns unchanged state
- [ ] Write test: rebuild from empty list
- [ ] Write test: rebuild from sequence
- [ ] Write test: original state unchanged (immutability)
- [ ] **✅ Verify: All projection tests pass**

### Step 6: State Manager with Rebuild
- [ ] Create `backend/state_manager.py`
- [ ] Implement `StateManager` class with `EventStore` dependency
- [ ] Add `_state` instance variable
- [ ] Add `_last_event_id` instance variable
- [ ] Add `threading.RLock` for thread safety
- [ ] Implement `_rebuild_state()` method
- [ ] Implement `_sync()` method
- [ ] Implement `get_state()` method
- [ ] Implement `get_agents()` method
- [ ] Implement `get_agent(name)` method
- [ ] Implement `get_chat_history(limit)` method
- [ ] Create `tests/test_state_manager.py`
- [ ] Write test: rebuild from empty store
- [ ] Write test: rebuild from events
- [ ] Write test: get_state returns current
- [ ] Write test: sync applies new events
- [ ] Write test: get_agents returns dict
- [ ] Write test: get_agent by name
- [ ] Write test: get_chat_history with limit
- [ ] Write test: thread safety
- [ ] **✅ Verify: State manager works correctly**

### Step 7: Snapshot System
- [ ] Create `backend/snapshot_manager.py`
- [ ] Implement `SnapshotManager` class
- [ ] Implement `should_snapshot(event_id)` method
- [ ] Implement `save_snapshot(state, event_id)` method
- [ ] Implement `load_latest_snapshot()` method
- [ ] Update `StateManager.__init__` to accept `SnapshotManager`
- [ ] Update `_rebuild_state()` to use snapshots
- [ ] Add `maybe_snapshot()` method
- [ ] Create `tests/test_snapshots.py`
- [ ] Write test: save and load snapshot
- [ ] Write test: load latest returns newest
- [ ] Write test: load latest returns None when empty
- [ ] Write test: state manager uses snapshot
- [ ] **✅ Verify: Snapshot system works, fast recovery**

---

## 📋 Phase 3: Command & Effect System

### Step 8: Command Handler (Pure Functions)
- [ ] Create `backend/effects.py` with `Effect` dataclass
- [ ] Create `backend/command_handler.py`
- [ ] Implement `CommandHandler` class
- [ ] Implement `handle_create_agent(name, system_prompt, model, template)`
- [ ] Implement `handle_command_agent(agent_name, command)`
- [ ] Implement `handle_user_message(message)`
- [ ] Add validation logic (agent exists, no duplicates)
- [ ] Return `tuple[list[int], list[Effect]]` from all handlers
- [ ] Create `tests/test_command_handler.py`
- [ ] Write test: handle_create_agent success
- [ ] Write test: handle_create_agent duplicate name error
- [ ] Write test: handle_command_agent success
- [ ] Write test: handle_command_agent nonexistent error
- [ ] Write test: handle_user_message
- [ ] Write test: events persisted in store
- [ ] **✅ Verify: Commands are pure, no side effects**

### Step 9: Effect Executor (Side Effects)
- [ ] Create `backend/effect_executor.py`
- [ ] Implement `EffectExecutor` class
- [ ] Add `claude_clients` dict instance variable
- [ ] Implement `async execute(effects)` method
- [ ] Implement `async _execute_one(effect)` method
- [ ] Implement `_create_claude_client(data)` (mock for now)
- [ ] Implement `_execute_agent_command(data)` (mock)
- [ ] Implement `_execute_orchestrator(data)` (mock)
- [ ] Add error handling (append `EFFECT_EXECUTION_FAILED`)
- [ ] Create `tests/test_effect_executor.py`
- [ ] Write test: execute create_claude_client
- [ ] Write test: execute agent_command
- [ ] Write test: execute orchestrator
- [ ] Write test: effect execution error
- [ ] Write test: multiple effects in sequence
- [ ] **✅ Verify: Effects execute, events logged**

### Step 10: Claude SDK Integration
- [ ] Update `effect_executor.py` to import Claude SDK
- [ ] Update `_create_claude_client` to use real SDK
- [ ] Update `_execute_agent_command` to use real SDK
- [ ] Update `_execute_orchestrator` to use real SDK
- [ ] Extract tokens and costs from SDK responses
- [ ] Append `TOOL_INVOKED` events for orchestrator tools
- [ ] Append `TOOL_RESULT_RECEIVED` events
- [ ] Create `tests/test_claude_integration.py`
- [ ] Write mock SDK tests OR mark as integration tests
- [ ] Add pytest configuration for integration tests
- [ ] Update existing tests to work with real SDK
- [ ] Add error handling for SDK errors
- [ ] **✅ Verify: SDK integration works (mock or real)**

---

## 📋 Phase 4: HTTP API Layer

### Step 11: Basic FastAPI Server with State Endpoints
- [ ] Create `backend/main.py` with FastAPI app
- [ ] Add CORS middleware
- [ ] Implement lifespan context manager
- [ ] Initialize `event_store` in lifespan
- [ ] Initialize `snapshot_manager` in lifespan
- [ ] Initialize `state_manager` in lifespan
- [ ] Store in `app.state`
- [ ] Add `GET /health` endpoint
- [ ] Add `GET /state` endpoint
- [ ] Add `GET /agents` endpoint
- [ ] Add `GET /agents/{name}` endpoint (with 404 handling)
- [ ] Add `GET /chat?limit=N` endpoint
- [ ] Add `GET /cost` endpoint
- [ ] Create `tests/test_api_basic.py`
- [ ] Create test fixture with TestClient
- [ ] Write test: health endpoint
- [ ] Write test: get state
- [ ] Write test: get agents
- [ ] Write test: get agent by name
- [ ] Write test: get agent not found (404)
- [ ] Write test: get chat history
- [ ] Write test: get cost summary
- [ ] **✅ Verify: All API endpoints work**

### Step 12: SSE Endpoint for Event Streaming
- [ ] Add `GET /events?since=N` endpoint to `main.py`
- [ ] Implement async generator `event_stream(request, since)`
- [ ] Send initial `STATE_SNAPSHOT` event
- [ ] Loop: check disconnect, get new events, yield SSE format
- [ ] Send keepalive messages when no events
- [ ] Add proper SSE headers (Cache-Control, Connection, etc.)
- [ ] Create `tests/test_sse.py`
- [ ] Write test: SSE connection
- [ ] Write test: initial snapshot sent
- [ ] Write test: events streamed
- [ ] Write test: since parameter works
- [ ] Write test: keepalive messages
- [ ] **✅ Verify: SSE streaming works, reconnects handled**

### Step 13: Command Endpoints
- [ ] Initialize `command_handler` in lifespan
- [ ] Initialize `effect_executor` in lifespan
- [ ] Create Pydantic request models (CreateAgentRequest, etc.)
- [ ] Add `POST /command/create_agent` endpoint
- [ ] Add `POST /command/command_agent` endpoint
- [ ] Add `POST /command/send_message` endpoint
- [ ] Execute effects in background tasks
- [ ] Return event IDs in response
- [ ] Create `tests/test_command_endpoints.py`
- [ ] Write test: create_agent endpoint
- [ ] Write test: command_agent endpoint
- [ ] Write test: send_message endpoint
- [ ] Write test: duplicate agent error
- [ ] Write test: nonexistent agent error
- [ ] Write test: events appear in SSE stream
- [ ] **✅ Verify: Commands work, effects execute async**

---

## 📋 Phase 5: Frontend Integration

### Step 14: SSE Client with Auto-Reconnect
- [ ] Create `frontend/src/services/sseClient.ts`
- [ ] Implement `SSEClient` class
- [ ] Add private properties (eventSource, lastEventId, retryCount)
- [ ] Implement `connect(onEvent, onError)` method
- [ ] Setup EventSource with URL
- [ ] Setup onmessage handler (parse JSON, call callback)
- [ ] Setup onerror handler (log, close, reconnect)
- [ ] Implement `reconnect(onEvent, onError)` method
- [ ] Implement exponential backoff calculation
- [ ] Implement `disconnect()` method
- [ ] Export singleton instance
- [ ] Create `frontend/src/services/sseClient.test.ts`
- [ ] Mock EventSource globally
- [ ] Write test: connect creates EventSource
- [ ] Write test: onmessage parses JSON
- [ ] Write test: onerror triggers reconnect
- [ ] Write test: exponential backoff
- [ ] Write test: disconnect closes connection
- [ ] **✅ Verify: SSE client works, reconnects automatically**

### Step 15: Event-Driven Pinia Store
- [ ] Update `frontend/src/stores/orchestratorStore.ts`
- [ ] Add state properties (orchestratorId, agents, chatHistory, etc.)
- [ ] Add `connected` and `lastEventId` state
- [ ] Implement `connectSSE()` action
- [ ] Implement `disconnectSSE()` action
- [ ] Implement `applyEvent(event)` action with switch statement
- [ ] Handle `STATE_SNAPSHOT` event
- [ ] Handle `AGENT_CREATED` event
- [ ] Handle `AGENT_STATUS_CHANGED` event
- [ ] Handle `COST_INCURRED` event
- [ ] Handle `USER_MESSAGE_RECEIVED` event
- [ ] Handle `ORCHESTRATOR_RESPONSE_GENERATED` event
- [ ] Handle `AGENT_DELETED` event
- [ ] Implement `handleError(error)` action
- [ ] Add getters (agentList, getAgent)
- [ ] Create `frontend/src/stores/orchestratorStore.test.ts`
- [ ] Write test: connectSSE calls sseClient
- [ ] Write test: apply_agent_created event
- [ ] Write test: apply_cost_incurred event
- [ ] Write test: apply_user_message event
- [ ] Write test: state_snapshot replaces state
- [ ] **✅ Verify: Store is event-driven, reactive**

### Step 16: UI Component Updates
- [ ] Update `frontend/src/App.vue`
- [ ] Call `orchestratorStore.connectSSE()` on mount
- [ ] Call `orchestratorStore.disconnectSSE()` on unmount
- [ ] Remove polling logic
- [ ] Update `frontend/src/components/AgentList.vue`
- [ ] Use `orchestratorStore.agentList` computed
- [ ] Remove REST API calls
- [ ] Update `frontend/src/components/OrchestratorChat.vue`
- [ ] Use `orchestratorStore.chatHistory` computed
- [ ] Send messages via API (don't wait for response)
- [ ] Messages appear via SSE
- [ ] Remove polling
- [ ] Update `frontend/src/components/EventStream.vue`
- [ ] Add connection status indicator
- [ ] Show `orchestratorStore.connected`
- [ ] Create component tests
- [ ] Write test: AgentList renders agents
- [ ] Write test: OrchestratorChat sends messages
- [ ] Write test: Components react to store updates
- [ ] **✅ Verify: UI updates in real-time, no polling**

---

## 📋 Phase 6: Migration & Cleanup

### Step 17: Dual-Write to Both Systems
- [ ] Create `backend/dual_write.py`
- [ ] Implement `DualWriteWrapper` class
- [ ] Implement `create_agent()` (write to both)
- [ ] Implement `command_agent()` (write to both)
- [ ] Implement `log_cost()` (write to both)
- [ ] Update `backend/main.py` to use dual-write
- [ ] Initialize both PostgreSQL and event store
- [ ] Continue reading from PostgreSQL
- [ ] Create `scripts/compare_states.py`
- [ ] Compare agent count between systems
- [ ] Compare agent names
- [ ] Compare total costs
- [ ] Compare chat message count
- [ ] Report any differences
- [ ] Create `tests/test_dual_write.py`
- [ ] Write test: agent created in both
- [ ] Write test: costs match in both
- [ ] Write test: comparison script
- [ ] **✅ Verify: Both systems have identical data**

### Step 18: Data Migration from PostgreSQL
- [ ] Create `scripts/migrate_postgresql_to_events.py`
- [ ] Connect to PostgreSQL
- [ ] Generate events from `orchestrator_agents` table
- [ ] Generate events from `agents` table
- [ ] Generate events from `prompts` table
- [ ] Generate events from `agent_logs` table
- [ ] Preserve timestamp ordering
- [ ] Append all events to event store
- [ ] Add validation (event count = row count)
- [ ] Create `scripts/validate_migration.py`
- [ ] Load state from both systems
- [ ] Deep compare all fields
- [ ] Generate detailed diff report
- [ ] Exit with error if differences found
- [ ] Add --dry-run flag to migration script
- [ ] Add progress bars (tqdm)
- [ ] Add resume capability
- [ ] Create backup before migration
- [ ] Create `tests/test_migration.py`
- [ ] Write test: events created correctly
- [ ] Write test: state matches after migration
- [ ] **✅ Verify: All data migrated, states match**

### Step 19: Remove PostgreSQL Dependencies
- [ ] Update `backend/main.py` to remove PostgreSQL init
- [ ] Remove DualWriteWrapper usage
- [ ] Use event_store directly
- [ ] Remove asyncpg imports
- [ ] Delete `backend/modules/database.py`
- [ ] Delete `backend/modules/websocket_manager.py`
- [ ] Delete `backend/modules/orchestrator_hooks.py`
- [ ] Delete `backend/modules/command_agent_hooks.py`
- [ ] Delete all hook files in `backend/modules/`
- [ ] Update `requirements.txt` (remove asyncpg)
- [ ] Update `pyproject.toml` or `setup.py`
- [ ] Update all imports throughout codebase
- [ ] Remove PostgreSQL-specific tests
- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Create `scripts/measure_code_reduction.py`
- [ ] Count LOC in old system
- [ ] Count LOC in new system
- [ ] Calculate reduction percentage
- [ ] Generate report
- [ ] Update README.md (remove PostgreSQL instructions)
- [ ] Update documentation with SQLite instructions
- [ ] Document breaking changes
- [ ] Create git commit with clear message
- [ ] **✅ Verify: All tests pass, 70% code reduction achieved**

### Step 20: Performance Optimization & Production Deploy
- [ ] Create `scripts/benchmark.py`
- [ ] Measure event append rate
- [ ] Measure query performance
- [ ] Measure state rebuild time
- [ ] Measure SSE latency
- [ ] Generate performance report
- [ ] Optimize based on benchmarks (if needed)
- [ ] Create `Dockerfile`
- [ ] Create `docker-compose.yml`
- [ ] Add health checks to Docker
- [ ] Create `docs/DEPLOYMENT.md`
- [ ] Document environment variables
- [ ] Document volume mounts
- [ ] Document backup strategy
- [ ] Add Prometheus metrics endpoint
- [ ] Create Grafana dashboard config
- [ ] Create alert rules
- [ ] Create `scripts/backup_events.sh`
- [ ] Implement backup rotation
- [ ] Verify backup integrity
- [ ] Create `tests/test_performance.py`
- [ ] Write test: append rate >1000/s
- [ ] Write test: query latency <10ms
- [ ] Write test: rebuild latency <1ms per 1000 events
- [ ] Write test: SSE latency <100ms
- [ ] Run full system test with Docker
- [ ] Run performance benchmarks
- [ ] Run full test suite with coverage
- [ ] Check code coverage (>80%)
- [ ] **✅ Verify: Performance targets met, production-ready**

---

## 📊 Production Checklist

### Pre-Deployment
- [ ] All 20 steps completed
- [ ] All tests passing (unit, integration, E2E)
- [ ] Code coverage >80%
- [ ] Performance benchmarks met
- [ ] Security audit completed
- [ ] Backup strategy in place
- [ ] Monitoring configured
- [ ] Documentation updated
- [ ] Rollback plan documented
- [ ] Load testing completed

### Deployment
- [ ] Backup current system
- [ ] Deploy new containers
- [ ] Run migration script
- [ ] Verify data integrity
- [ ] Monitor for 24 hours
- [ ] Check error rates
- [ ] Check performance metrics
- [ ] Verify user functionality

### Post-Deployment
- [ ] Monitor system health (1 week)
- [ ] Collect user feedback
- [ ] Address any issues
- [ ] Update documentation based on learnings
- [ ] Archive old PostgreSQL code
- [ ] Celebrate success! 🎉

---

## 📈 Success Metrics

- [ ] **Code Reduction**: 70% fewer lines (5136 LOC → 1540 LOC)
- [ ] **Setup Simplicity**: Zero PostgreSQL config required
- [ ] **Performance**: <1ms event append, <10ms queries
- [ ] **Reliability**: SSE auto-reconnect working
- [ ] **Testability**: 100% pure functions, no mocks needed
- [ ] **Debuggability**: Full event history, time travel capability

---

## 🚨 Rollback Plan (If Needed)

- [ ] Keep PostgreSQL migrations (don't delete immediately)
- [ ] Maintain dual-write for 1 week post-deployment
- [ ] Have script to sync from events back to PostgreSQL
- [ ] Document rollback procedure
- [ ] Test rollback in staging environment

---

## 📝 Notes

- Each checkbox represents a concrete, testable task
- Don't skip steps - they build on each other
- Run tests after each step before moving forward
- Use git commits at major milestones
- Keep `events.db` backed up during development
- Document any deviations from the plan

---

**Start Date**: _____________  
**Target Completion**: _____________  
**Actual Completion**: _____________

**Team Members**:
- [ ] ____________________
- [ ] ____________________
- [ ] ____________________

**Estimated Effort**: 4-6 weeks (20 steps × 1-2 hours each + integration time)