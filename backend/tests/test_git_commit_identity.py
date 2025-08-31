import subprocess

from ai_org_backend.services import storage


def test_git_commit_without_user(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    # Ensure git sees no global configuration
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_NAME", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_EMAIL", raising=False)
    subprocess.run(["git", "init"], cwd=repo, check=True)
    (repo / "file.txt").write_text("data")
    monkeypatch.setattr(storage, "WORKSPACE", repo)
    storage._git_commit("file.txt", "test")
    out = subprocess.check_output(
        ["git", "-C", str(repo), "log", "-1", "--format=%an <%ae>"],
        text=True,
    ).strip()
    assert out == "ai-org-bot <noreply@ai.org>"
