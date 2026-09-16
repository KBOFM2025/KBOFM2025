"""경기 결과를 소비하는 2D 구장. 연출은 엔진 결과나 난수열을 변경하지 않는다."""
import math
import time
from copy import deepcopy

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QLinearGradient
from PySide6.QtWidgets import QWidget
from app.player_photos import resolve_player_photo


POSITIONS = {
    "LF": (.23, .29), "CF": (.5, .21), "RF": (.77, .29),
    "3B": (.28, .53), "SS": (.40, .43), "2B": (.60, .43),
    "1B": (.72, .53), "P": (.5, .59), "C": (.5, .83),
}
BASES = {0: (.5, .79), 1: (.71, .61), 2: (.5, .43), 3: (.29, .61), 4: (.5, .79)}
CONTACT = {"1B", "2B", "3B", "HR", "OUT", "ROE", "FOUL"}


def runner_paths(before, after, event):
    """실제 베이스 점유와 득점 기록으로 진루 경로를 정한다. 사라진 주자를 득점으로 추측하지 않는다."""
    starts = {int(pid): int(base) for base, pid in before.get("bases", {}).items() if pid is not None}
    code = event.get("result_code")
    if code in {"1B", "2B", "3B", "HR", "BB", "ROE", "OUT"} and event.get("batter_id"):
        starts[int(event["batter_id"])] = 0
    ends = {int(pid): int(base) for base, pid in event.get("bases_after", {}).items() if pid is not None}
    offense = before.get("offense_team")
    paths = []
    for pid, start in starts.items():
        key = f"{offense}|{pid}"
        scored = after.get("stats", {}).get(key, {}).get("runs", 0) > before.get("stats", {}).get(key, {}).get("runs", 0)
        end = 4 if scored else ends.get(pid, start)
        if code == "CS" and start == 1 and pid not in ends:
            end = 2
        elif code == "OUT" and start == 0 and "땅볼" in event.get("description", ""):
            end = 1
        if end > start:
            paths.append((pid, list(range(start, end + 1))))
    return paths


class LiveBaseballField(QWidget):
    animation_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(430, 360)
        self.state = {}
        self.player = {}
        self.season = {}
        self.game_stat = {}
        self.roster = []
        self.maps = {}
        self._photos = {}
        self._stadium = QPixmap()
        self._stadium_path = None
        self._park_cache = QPixmap()
        self._park_key = None
        self.play_event = {}
        self.active = False
        self.progress = 0.0
        self.paths = []
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

    def set_state(self, state):
        self.state = deepcopy(state or {})
        self.update()

    def set_defenders(self, roster, maps):
        self.roster, self.maps = roster, maps

    def set_broadcast_context(self, stadium_path, player, season, game_stat=None):
        if str(stadium_path) != self._stadium_path:
            self._stadium_path = str(stadium_path)
            self._stadium = QPixmap(str(stadium_path)) if stadium_path else QPixmap()
        self.player, self.season, self.game_stat = player or {}, season or {}, game_stat or {}
        self.update()

    def animate_play(self, before, after, event, speed=1.0):
        self.state = deepcopy(before)
        self.play_event = dict(event)
        self.paths = runner_paths(before, after, event)
        self.progress = 0.0
        self.duration = (2.7 if event.get("result_code") in CONTACT or self.paths else 1.5) / speed
        self.started = time.monotonic()
        self.active = True
        self.timer.start()
        self.update()

    def cancel_animation(self):
        self.timer.stop()
        self.active = False
        self.update()

    def _tick(self):
        self.progress = min(1.0, (time.monotonic() - self.started) / self.duration)
        self.update()
        if self.progress >= 1:
            self.timer.stop()
            self.active = False
            self.animation_finished.emit()

    def _photo(self, player):
        key = (player.get("id"), player.get("name"), player.get("team"))
        if key not in self._photos:
            path = resolve_player_photo(player.get("kbo_player_id"), player.get("name"), player.get("team"))
            self._photos[key] = QPixmap(str(path)) if path else QPixmap()
        return self._photos[key]

    @staticmethod
    def _lerp(a, b, t):
        return QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        point = lambda xy: QPointF(xy[0] * w, xy[1] * h)
        self._draw_park(p, w, h)
        mound = point(POSITIONS["P"])

        defense = self.state.get("defense_team", "")
        defenders = {r.get("position"): r for r in self.roster if r.get("team") == defense and r.get("role") == "batter"}
        defenders["P"] = {"player_id": self.state.get("pitcher_id"), "player_name": self.state.get("pitcher_name", "")}
        code = self.play_event.get("result_code", "")
        contact = code in CONTACT
        # 타구 방향은 결과를 설명하는 연출 좌표이며 실측 궤적은 아니다.
        direction = int(self.play_event.get("sequence_no", 0)) % 3
        target_pos = ("LF", "CF", "RF")[direction] if code != "OUT" or "땅볼" not in self.play_event.get("description", "") else ("3B", "SS", "2B")[direction]
        target = point(POSITIONS[target_pos])
        if code == "HR":
            target = point(((.22, .5, .78)[direction], .10))
        elif code == "FOUL":
            target = point((.06, .67))
        phase = max(0.0, min(1.0, (self.progress - .38) / .48))
        for position, xy in POSITIONS.items():
            entry = defenders.get(position, {})
            player = self.maps.get(defense, {}).get(int(entry.get("player_id") or 0), entry)
            center = point(xy)
            if self.active and position == "P" and self.progress < .38 and code not in {"PITCH_CHANGE", "SB", "CS"}:
                center += QPointF(0, -8 * math.sin(min(1, self.progress / .38) * math.pi))
            if self.active and contact and position == target_pos and code not in {"HR", "FOUL"}:
                center += QPointF(0, -h * .025 * math.sin(phase * math.pi))
            self._draw_player(p, center, position, player, QColor("#ffc76b") if position == "P" else QColor("#85cad9"))
        batter_center = point((.45, .79))
        batter_running = self.active and phase > 0 and any(pid == self.play_event.get("batter_id") for pid, _ in self.paths)
        if not batter_running:
            self._draw_player(p, batter_center, "타석", self.player, QColor("#f3c46a"))
        if self.active and not batter_running and code not in {"BALL", "CALLED_STRIKE", "BB", "PITCH_CHANGE", "SB", "CS"}:
            angle = -.8 + max(0, min(1, (self.progress - .30) / .12)) * 2.3
            p.setPen(QPen(QColor("#f4d397"), 4))
            p.drawLine(batter_center, batter_center + QPointF(math.cos(angle)*30, math.sin(angle)*20))

        moving = {pid for pid, _ in self.paths} if self.active else set()
        for base, pid in self.state.get("bases", {}).items():
            if pid is not None and int(pid) not in moving:
                self._runner(p, point(BASES[int(base)]), pid)
        if self.active:
            for pid, route in self.paths:
                travel = phase * (len(route) - 1)
                segment = min(int(travel), len(route)-2)
                a, b = point(BASES[route[segment]]), point(BASES[route[segment+1]])
                self._runner(p, self._lerp(a, b, travel-segment), pid)
            if code != "PITCH_CHANGE":
                home = point(BASES[0])
                if code in {"SB", "CS"}:
                    ball = self._lerp(home, point(BASES[2]), phase)
                elif self.progress < .38:
                    ball = self._lerp(mound, home, max(0, (self.progress - .12) / .26))
                else:
                    ball = self._lerp(home, target, phase) if contact else home
                    if code == "OUT" and "땅볼" in self.play_event.get("description", ""):
                        ball = self._lerp(home, target, min(1, phase * 1.7)) if phase < .6 else self._lerp(target, point(POSITIONS["1B"]), (phase-.6)/.4)
                    if contact and code != "OUT":
                        ball += QPointF(0, -h * .07 * math.sin(phase * math.pi))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 218, 107, 65))
                p.drawEllipse(ball, 9, 9)
                p.setBrush(QColor("#ffffff"))
                p.drawEllipse(ball, 4, 4)
        p.setPen(QColor("#ecf5fa"))
        p.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        phase_text = ("투수 준비" if self.progress < .12 else "투구" if self.progress < .38 else "타격 · 수비 · 주루" if contact else "판정") if self.active else "다음 투구 대기"
        if self.active and code == "PITCH_CHANGE":
            phase_text = "투수 교체"
        if self.active and code in {"SB", "CS"}:
            phase_text = "도루 · 송구"
        p.fillRect(QRectF(12, 10, min(350, w * .47), 27), QColor(7, 18, 28, 220))
        p.fillRect(QRectF(12, 10, 3, 27), QColor("#efb85d"))
        p.drawText(QRectF(23, 10, min(335, w * .44), 27), Qt.AlignmentFlag.AlignVCenter, f"{defense} 수비  ·  {phase_text}")
        caption = self.play_event.get("description", "") if not self.active or self.progress > .82 else ""
        p.fillRect(QRectF(0, h-52, w, 52), QColor(6, 17, 27, 230))
        p.drawText(QRectF(14, h-48, w-28, 24), Qt.AlignmentFlag.AlignVCenter, caption or f"타자 {self.player.get('name', '-')} · 투수 {self.state.get('pitcher_name', '-')}")
        p.setFont(QFont("Malgun Gothic", 10))
        p.setPen(QColor("#97b6c7"))
        p.drawText(QRectF(14, h-25, w-28, 22), f"시즌 AVG {self.season.get('AVG', '-')}  OPS {self.season.get('OPS', '-')}  ·  오늘 {self.game_stat.get('at_bats', 0)}타수 {self.game_stat.get('hits', 0)}안타")
        p.end()

    def _draw_player(self, p, center, position, player, color):
        self._sprite(p, center, color, position)
        photo = self._photo(player)
        width = min(156, max(114, self.width() * .14))
        rect = QRectF(center.x()-width/2, center.y()+8, width, 25)
        p.setPen(QPen(QColor(0, 0, 0, 75), 1))
        p.setBrush(QColor(5, 19, 29, 235))
        p.drawRoundedRect(rect, 3, 3)
        p.fillRect(QRectF(rect.left(), rect.top(), 3, rect.height()), color)
        p.save()
        clip = QPainterPath()
        portrait = QRectF(rect.left()+6, rect.top()+3, 19, 19)
        clip.addRoundedRect(portrait, 2, 2)
        p.setClipPath(clip)
        if not photo.isNull():
            p.drawPixmap(portrait, photo, QRectF(photo.rect()))
        p.restore()
        p.setPen(color)
        p.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        name = player.get('name') or player.get('player_name') or '-'
        text_rect = rect.adjusted(29, 0, -4, 0)
        text = p.fontMetrics().elidedText(f"{position} {name}", Qt.TextElideMode.ElideRight, int(text_rect.width()))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)

    def _sprite(self, p, center, color, position="주자"):
        p.save()
        p.translate(center)
        scale = max(.72, min(1.15, self.height()/500))
        p.scale(scale, scale)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 75))
        p.drawEllipse(QRectF(-10, -1, 24, 7))
        if position in {"P", "타석"}:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(color, 1.5))
            p.drawEllipse(QRectF(-14, -4, 28, 10))
        step = math.sin(self.progress * 24) * 3 if self.active and position == "주자" else 0
        p.setPen(QPen(QColor("#dce5ea"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(-3, -9), QPointF(-5-step, 0))
        p.drawLine(QPointF(3, -9), QPointF(5+step, 0))
        p.setPen(QPen(QColor("#1c2939"), 3))
        p.drawLine(QPointF(-6-step, 1), QPointF(-2-step, 1))
        p.drawLine(QPointF(3+step, 1), QPointF(7+step, 1))
        p.setBrush(QColor("#eff2ee"))
        p.setPen(QPen(QColor("#263a47"), .8))
        p.drawRoundedRect(QRectF(-6, -21, 12, 13), 3, 3)
        p.fillRect(QRectF(-1, -20, 2, 11), color)
        lift = -7 * math.sin(min(1, self.progress/.38)*math.pi) if self.active and position == "P" and self.progress < .38 else 0
        p.setPen(QPen(QColor("#d8b295"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(-6, -19), QPointF(-10, -12))
        p.drawLine(QPointF(6, -19), QPointF(10, -13+lift))
        p.setBrush(QColor("#8b5b31"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(-13, -15, 6, 6))
        p.setBrush(QColor("#dabb9f"))
        p.drawEllipse(QRectF(-4, -29, 8, 9))
        p.setBrush(color.darker(165))
        p.drawRoundedRect(QRectF(-5, -31, 10, 5), 2, 2)
        p.fillRect(QRectF(-5, -27, 13, 2), color.darker(140))
        p.restore()

    def _runner(self, p, center, pid):
        self._sprite(p, center, QColor("#ffc65e"))
        p.setPen(QColor("#fff2cf"))
        player = self.maps.get(self.state.get("offense_team"), {}).get(int(pid), {})
        p.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        p.drawText(QRectF(center.x()-45, center.y()-52, 90, 18), Qt.AlignmentFlag.AlignCenter, player.get("name", "주자"))

    def _draw_park(self, painter, w, h):
        key = (w, h, self.devicePixelRatioF(), self.state.get("home_team"))
        if self._park_key == key:
            painter.drawPixmap(0, 0, self._park_cache)
            return
        ratio = self.devicePixelRatioF()
        self._park_cache = QPixmap(round(w*ratio), round(h*ratio))
        self._park_cache.setDevicePixelRatio(ratio)
        self._park_key = key
        p = QPainter(self._park_cache)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        point = lambda xy: QPointF(xy[0]*w, xy[1]*h)
        sky = QLinearGradient(0, 0, 0, h)
        sky.setColorAt(0, QColor("#172e40"))
        sky.setColorAt(.6, QColor("#263b3c"))
        sky.setColorAt(1, QColor("#101f2c"))
        p.fillRect(QRectF(0, 0, w, h), sky)
        # 한 시점으로 이어지는 관중석. 좌석·통로·외야 벽을 배경 캐시에 그린다.
        p.setPen(Qt.PenStyle.NoPen)
        palette = ("#713d40", "#955449", "#444f5c", "#d3b79c", "#afb8b8", "#435c6b")
        for row in range(13):
            for seat in range(130):
                if seat % 19 < 2:
                    continue
                t = seat/129
                x = (.035 + .93*t)*w
                y = (.143 + .27*(2*t-1)**2 - row*.009)*h
                p.setBrush(QColor(palette[(seat*7+row*11) % len(palette)]))
                p.drawRoundedRect(QRectF(x, y, max(2,w*.004), max(2,h*.006)), 1, 1)
        # 중앙 전광판과 양측 조명탑.
        p.fillRect(QRectF(w*.395, h*.035, w*.21, h*.075), QColor("#07151e"))
        p.fillRect(QRectF(w*.395, h*.035, w*.21, 3), QColor("#bf965c"))
        p.setPen(QColor("#e5cf9f"))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.drawText(QRectF(w*.395, h*.045, w*.21, h*.05), Qt.AlignmentFlag.AlignCenter, "KBO FM  •  BALLPARK")
        for x in (.16, .84):
            p.setPen(QPen(QColor("#8fa1a5"), 2))
            p.drawLine(point((x,.12)), point((x,.035)))
            p.fillRect(QRectF(w*x-20,h*.028,40,10), QColor("#e9dec3"))
        field = QPainterPath(point(BASES[0]))
        field.lineTo(point((.055,.39)))
        field.cubicTo(point((.15,.03)), point((.85,.03)), point((.945,.39)))
        field.closeSubpath()
        p.setPen(QPen(QColor("#987950"), max(8,h*.027)))
        p.setBrush(QColor("#44823e"))
        p.drawPath(field)
        grass = QLinearGradient(0,h*.12,0,h*.83)
        grass.setColorAt(0,QColor("#347146"))
        grass.setColorAt(.5,QColor("#57934b"))
        grass.setColorAt(1,QColor("#76a857"))
        p.fillPath(field,grass)
        p.save()
        p.setClipPath(field)
        p.setPen(Qt.PenStyle.NoPen)
        for stripe in range(22):
            band = QPainterPath(point((stripe*.08-.7,0)))
            for xy in ((stripe*.08-.64,0),(stripe*.08+.36,1),(stripe*.08+.3,1)):
                band.lineTo(point(xy))
            band.closeSubpath()
            p.fillPath(band,QColor(198,227,132,17))
        # 내야 흙과 잔디 다이아몬드.
        p.setBrush(QColor("#bd9365"))
        p.drawEllipse(QRectF(w*.255,h*.402,w*.49,h*.397))
        p.setBrush(QColor("#caa274"))
        p.drawEllipse(QRectF(w*.27,h*.415,w*.46,h*.38))
        inner = QPainterPath(point((.5,.745)))
        for xy in ((.657,.605),(.5,.47),(.343,.605)):
            inner.lineTo(point(xy))
        inner.closeSubpath()
        p.fillPath(inner,grass)
        p.restore()
        # 외야 펜스, 구역 표시, 파울 폴.
        wall = QPainterPath(point((.055,.39)))
        wall.cubicTo(point((.15,.03)),point((.85,.03)),point((.945,.39)))
        p.setPen(QPen(QColor("#183a36"),max(10,h*.032)))
        p.drawPath(wall)
        p.setPen(QPen(QColor("#dfb851"),2))
        p.drawPath(wall)
        p.setFont(QFont("Segoe UI",10,QFont.Weight.Bold))
        p.setPen(QColor("#e6dbc2"))
        for text, xy in (("LEFT FIELD",(.15,.265)),("CENTER FIELD",(.5,.135)),("RIGHT FIELD",(.85,.265))):
            pos=point(xy)
            p.drawText(QRectF(pos.x()-60,pos.y()-10,120,20),Qt.AlignmentFlag.AlignCenter,text)
        for end in ((.055,.39),(.945,.39)):
            p.setPen(QPen(QColor("#f0ece0"),1.5))
            p.drawLine(point(BASES[0]),point(end))
            p.setPen(QPen(QColor("#e5be48"),3))
            p.drawLine(point(end),point((end[0],end[1]-.12)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#d6b18a"))
        p.drawEllipse(point(POSITIONS["P"]),w*.022,h*.024)
        p.drawEllipse(point(BASES[0]),w*.026,h*.035)
        for base in (1,2,3):
            b=point(BASES[base])
            p.save()
            p.translate(b)
            p.rotate(40 if base != 2 else 0)
            p.fillRect(QRectF(-4,-3,8,6),QColor("#ffffee"))
            p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#f9f1d9"),1))
        for offset in (-.024,.014):
            p.drawRect(QRectF(w*(.5+offset),h*.775,w*.011,h*.028))
        p.fillRect(QRectF(w*.495,h*.588,w*.01,3),QColor("#fff9e9"))
        home=point(BASES[0])
        p.fillRect(QRectF(home.x()-4,home.y()-2,8,5),QColor("#fff9e9"))
        # 투수·타자 쪽 파울 지역과 더그아웃.
        for x in (.06,.80):
            p.fillRect(QRectF(w*x,h*.71,w*.14,h*.035),QColor("#091f2b"))
            p.fillRect(QRectF(w*x,h*.705,w*.14,3),QColor("#768e99"))
            p.setPen(QColor("#92a9b2"))
            p.setFont(QFont("Segoe UI",10,QFont.Weight.Bold))
            p.drawText(QRectF(w*x,h*.71,w*.14,h*.035),Qt.AlignmentFlag.AlignCenter,"HOME DUGOUT" if x < .5 else "AWAY DUGOUT")
        p.end()
        painter.drawPixmap(0,0,self._park_cache)
