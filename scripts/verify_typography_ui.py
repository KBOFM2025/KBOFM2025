"""실제 선수 데이터와 공통 스타일로 글꼴 확대 후 밀집 화면을 렌더링한다."""
import os
import sys
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "venv/Lib/site-packages")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from app.styles import GLOBAL_STYLE
from app.views.team_manage.player_profile import PlayerProfilePage
from app.views.contract_negotiation import AgentContractNegotiationWidget


def main():
    app = QApplication([])
    for filename in ("malgun.ttf", "malgunbd.ttf"):
        QFontDatabase.addApplicationFont(f"C:/Windows/Fonts/{filename}")
    app.setFont(QFont("Malgun Gothic", 11))
    app.setStyleSheet(GLOBAL_STYLE)
    output = ROOT / "tmp/typography"
    output.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect((ROOT / "data/players.db").as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        player = dict(connection.execute("SELECT * FROM players WHERE name='김도영' LIMIT 1").fetchone())
    profile = PlayerProfilePage()
    profile.set_player(player)
    contract = AgentContractNegotiationWidget()
    contract.gate.hide()
    contract.player_name.setText(player["name"])
    contract.title.setText("김도영 계약 조건 협상")
    for name, page in (("profile", profile), ("contract", contract)):
        page.resize(1600, 960)
        page.show()
        app.processEvents()
        assert page.grab().save(str(output / f"{name}.png"), "PNG")
        page.close()
    print(f"Typography screens rendered: {output}")


if __name__ == "__main__":
    main()
