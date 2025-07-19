import os, json, pytest, uuid, asyncio
from pathlib import Path
from sqlmodel import Session

# Assume ai_org_prototype is importable in tests context
import ai_org_prototype as app

FIXTURE_FILE = Path(__file__).parent / 'fixtures' / 'tasks.json'

@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_eval_suite(tmp_path, monkeypatch):
    """Runs 20 synthetic tasks through orchestrator; expects ≥ 95% PASS."""
    # Load fixture tasks
    tasks = json.loads(FIXTURE_FILE.read_text())

    # Set synthetic on
    monkeypatch.setitem(os.sys.modules['__main__'].__dict__, 'SYNTHETIC', True)

    tenant_id = 'test-' + uuid.uuid4().hex[:6]
    repo = app.Repo(tenant_id)

    # Seed tasks
    for tdata in tasks:
        repo.add_task(tdata['description'], tdata['value'])

    # Run orchestrator loop once synchronously (Celery eager) – limit iterations
    await app.orchestrator_loop(budget=100, max_iters=5)

    # Collect pass/fail
    with Session(app.engine) as s:
        done = s.exec(app.select(app.TaskDB).where(app.TaskDB.tenant_id==tenant_id)).all()
    passed = [t for t in done if t.status == 'done']
    pass_rate = len(passed) / len(done)
    assert pass_rate >= 0.95, f'Pass rate {pass_rate:.2%} below threshold'
