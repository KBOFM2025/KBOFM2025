import urllib.request
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap


class PlayerProfileDialog(QDialog):
    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self.setWindowTitle(f"선수 보고서 - {player['name']}")
        self.resize(650, 550)

        # FM 스타일 다크 스킨
        self.setStyleSheet("""
            QDialog { background-color: #0b1220; }
            QLabel { font-family: 'Malgun Gothic'; color: #e2e8f0; }
            QFrame#card { background-color: #070d19; border: 1px solid #1e293b; border-radius: 8px; }
            QFrame#section { background-color: #0f172a; border-radius: 6px; padding: 10px; }
            QLabel#pro_text { color: #4ade80; }
            QLabel#con_text { color: #f87171; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # ----------------------------------------------------
        # [1] 상단: 헤더 영역 (실제 선수 사진 연동 공간)
        # ----------------------------------------------------
        header_frame = QFrame()
        header_frame.setObjectName("card")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 15, 15, 15)

        # 💡 선수 사진 레이블 세팅
        avatar = QLabel()
        avatar.setFixedSize(90, 110)  # 야구 카드 비율 프로필 사이즈
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet("border: 1px solid #1e293b; background-color: #030a16; border-radius: 4px;")

        try:
            # NC 다이노스 공식 홈페이지 선수 이미지 서버 URL 매칭 규칙 적용
            # 각 선수별 영문명 매칭 딕셔너리
            eng_names = {
                "박민우": "https://ncdinos-common-bucket.s3.ap-northeast-2.amazonaws.com/v1/player/9a2afbc0314a4b68b2edd9c865258ae0_20260126_032809.jpg", "데이비슨": "davidson", "김휘집": "kimhwejip",
                "김주원": "kimjuwon", "서호철": "seohochul", "권희동": "kwonheedong",
                "박한결": "parkhangyeol", "김형준": "kimhyungjun", "한건희": "hangeonhee",
                "신민혁": "shinminhyuk", "김영규": "kimyoungkyu", "류진욱": "ryujinwook",
                "김재열": "kimjaeyeol", "목지훈": "mokjihun", "김태우": "kimtaewoo",
                "신용석": "shinyongseok", "김범준": "kimbeomjun"
            }

            eng_name = eng_names.get(player["name"], "ci_dinos")
            img_url = f"https://ncdinos-common-bucket.s3.ap-northeast-2.amazonaws.com/v1/player/9a2afbc0314a4b68b2edd9c865258ae0_20260126_032809.jpg"

            # 이미지 다운로드 및 뷰어 세팅
            req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})
            data = urllib.request.urlopen(req, timeout=3).read()
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            avatar.setPixmap(pixmap.scaled(avatar.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        except Exception:
            # 실패 시 백업 공룡 텍스트
            avatar.setText("🦕")
            avatar.setFont(QFont("Arial", 28))

        header_layout.addWidget(avatar)
        header_layout.addSpacing(10)

        info_vbox = QVBoxLayout()
        name_label = QLabel(player["name"])
        name_label.setFont(QFont("Malgun Gothic", 18, QFont.Bold))
        name_label.setStyleSheet("color: #af9154;")

        is_pitcher = (player["pos"] == "P")
        pos_text = "투수 (P)" if is_pitcher else f"야수 ({player['pos']})"
        detail_label = QLabel(f"보직: {pos_text}  |  나이: {player['age']}세")
        detail_label.setStyleSheet("color: #94a3b8;")

        info_vbox.addWidget(name_label)
        info_vbox.addWidget(detail_label)
        header_layout.addLayout(info_vbox)
        header_layout.addStretch()

        # 계약 및 연봉 정보
        contract_vbox = QVBoxLayout()
        contract_vbox.setAlignment(Qt.AlignRight)
        salary = player.get("salary", player["age"] * 1250)
        salary_label = QLabel(f"주급: ₩{int(salary / 52):,}만  (연봉: ₩{salary:,}만)")
        salary_label.setFont(QFont("Malgun Gothic", 10, QFont.Bold))
        value_label = QLabel(f"예상 가치: ₩{int(salary * 3.5):,}만")
        value_label.setStyleSheet("color: #38bdf8;")

        contract_vbox.addWidget(salary_label)
        contract_vbox.addWidget(value_label)
        header_layout.addLayout(contract_vbox)

        main_layout.addWidget(header_frame)

        # ----------------------------------------------------
        # [2] 중단: FM 스타일 기술/정신/신체 세부 스탯 패널
        # ----------------------------------------------------
        stats_frame = QFrame()
        stats_frame.setObjectName("card")
        stats_layout = QVBoxLayout(stats_frame)

        stats_title = QLabel("📊 기술 및 능력치 분석")
        stats_title.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        stats_title.setStyleSheet("color: #af9154; padding-left: 5px; padding-top: 5px;")
        stats_layout.addWidget(stats_title)

        grid = QGridLayout()
        grid.setContentsMargins(15, 10, 15, 15)
        grid.setSpacing(10)

        if is_pitcher:
            stat_labels = [
                ("구속 (Velocity)", player["con"]),
                ("제구력 (Control)", player["pow"]),
                ("변화구 (Movement)", player["eye"]),
                ("스태미나 (Stamina)", player["def"]),
                ("위기관리 (Clutch)", int(player["pow"] * 1.05)),
                ("구위 (Stuff)", int(player["con"] * 0.95))
            ]
        else:
            stat_labels = [
                ("정확성 (Contact)", player["con"]),
                ("장타력 (Power)", player["pow"]),
                ("선구안 (Eye)", player["eye"]),
                ("수비력 (Defense)", player["def"]),
                ("주력 (Pace)", int(player["con"] * 1.1) if player["age"] < 30 else int(player["con"] * 0.8)),
                ("멘탈 (Work Rate)", int(player["eye"] * 1.02))
            ]

        for i, (name, val) in enumerate(stat_labels):
            row = i // 2
            col = (i % 2) * 2

            lbl = QLabel(name)
            lbl.setStyleSheet("color: #94a3b8;")

            val_lbl = QLabel(str(min(val, 99)))
            val_lbl.setAlignment(Qt.AlignCenter)
            val_lbl.setFont(QFont("Arial", 10, QFont.Bold))

            if val >= 80:
                val_lbl.setStyleSheet(
                    "color: #10b981; background-color: #064e3b; border-radius: 4px; padding: 2px 8px;")
            elif val >= 60:
                val_lbl.setStyleSheet(
                    "color: #fbbf24; background-color: #78350f; border-radius: 4px; padding: 2px 8px;")
            else:
                val_lbl.setStyleSheet(
                    "color: #ef4444; background-color: #7f1d1d; border-radius: 4px; padding: 2px 8px;")

            grid.addWidget(lbl, row, col)
            grid.addWidget(val_lbl, row, col + 1)

        stats_layout.addLayout(grid)
        main_layout.addWidget(stats_frame)

        # ----------------------------------------------------
        # [3] 하단: 스카우팅 리포트 (장점 & 단점)
        # ----------------------------------------------------
        report_frame = QFrame()
        report_frame.setObjectName("card")
        report_layout = QVBoxLayout(report_frame)

        report_title = QLabel("📋 수석 코치 스카우팅 리포트")
        report_title.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        report_title.setStyleSheet("color: #af9154; padding-left: 5px;")
        report_layout.addWidget(report_title)

        h_box = QHBoxLayout()
        h_box.setSpacing(10)

        # 장점 생성 로직
        pro_frame = QFrame()
        pro_frame.setObjectName("section")
        pro_vbox = QVBoxLayout(pro_frame)
        pro_head = QLabel("➕ 장점 (Pros)")
        pro_head.setFont(QFont("Malgun Gothic", 10, QFont.Bold))
        pro_head.setStyleSheet("color: #4ade80;")
        pro_vbox.addWidget(pro_head)

        pros = []
        if player["con"] >= 80: pros.append("• 리그 최고 수준의 정확한 메커니즘 제공")
        if player["pow"] >= 80: pros.append("• 경기 흐름을 한 번에 바꿀 결정적 한 방 보유")
        if player["def"] >= 80: pros.append("• 수비 집중력이 높아 실책 위험이 매우 낮음")
        if player["age"] <= 25: pros.append("• 발전 가능성이 매우 높은 팀의 핵심 유망주")
        if not pros: pros.append("• 꾸준한 훈련 태도로 기량이 안정적임")

        for p in pros:
            p_lbl = QLabel(p)
            p_lbl.setWordWrap(True)
            pro_vbox.addWidget(p_lbl)
        pro_vbox.addStretch()

        # 단점 생성 로직
        con_frame = QFrame()
        con_frame.setObjectName("section")
        con_vbox = QVBoxLayout(con_frame)
        con_head = QLabel("➖ 단점 (Cons)")
        con_head.setFont(QFont("Malgun Gothic", 10, QFont.Bold))
        con_head.setStyleSheet("color: #f87171;")
        con_vbox.addWidget(con_head)

        cons = []
        if player["age"] >= 35: cons.append("• 에이징 커브 진행 중으로 체력 관리가 필요함")
        if player["pow"] < 60: cons.append("• 파워 수치가 아쉬워 장타 생산력이 부족함")
        if player["con"] < 65: cons.append("• 기복이 다소 존재하여 세밀함 보완 필요")
        if not cons: cons.append("• 특별한 단점이 없는 육각형 밸런스")

        for c in cons:
            c_lbl = QLabel(c)
            c_lbl.setWordWrap(True)
            con_vbox.addWidget(c_lbl)
        con_vbox.addStretch()

        h_box.addWidget(pro_frame)
        h_box.addWidget(con_frame)
        report_layout.addLayout(h_box)

        main_layout.addWidget(report_frame)