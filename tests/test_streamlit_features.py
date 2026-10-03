from pathlib import Path

def test_streamlit_dashboard_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "streamlit_app.py").exists()
    assert (root / ".streamlit" / "config.toml").exists()
    assert "streamlit" in (root / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "SpeechRecognition" in (root / "requirements.txt").read_text(encoding="utf-8")
    assert "pyttsx3" in (root / "requirements.txt").read_text(encoding="utf-8")

def test_docker_exposes_both_apps_in_compose():
    text=(Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    assert "5000:5000" in text
    assert "8501:8501" in text
    assert "streamlit run streamlit_app.py" in text
