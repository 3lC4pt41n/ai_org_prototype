import sys
sys.path.append('backend')

import types
sys.modules['llm'] = types.ModuleType('llm')
sys.modules['llm'].chat_completion = lambda prompt, **kw: prompt

from ai_org_backend.tasks.llm_tasks import render_dev

def test_render_dev_basic():
    prompt = render_dev(
        purpose="demo purpose",
        task="demo",
        business_value=1.0,
        tokens_plan=100,
        purpose_relevance=50,
    )
    assert "demo" in prompt
