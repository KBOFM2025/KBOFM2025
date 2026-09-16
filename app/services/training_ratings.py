"""Training performance, not player ability or guaranteed growth. Game-designed 1–10 scale."""
import json
from datetime import date, timedelta
from app.services.player_development import roll


def evaluate_training(save_id, player, state, day, training):
    day = day.isoformat() if isinstance(day, date) else str(day)
    status = ('국가대표 차출' if state.get('squad_group') == '국가대표' else
              '부상 재활' if state.get('injury_days', 0) > 0 else
              '휴식·회복' if training.get('focus') == '회복' or training.get('rest_day') else
              '훈련 없음' if training.get('sessions', 0) == 0 and training.get('training_gain', 0) <= 0 else '훈련 참여')
    if status != '훈련 참여':
        return dict(rating=None, participation=status, factors={})
    # Stable individual/day response: reloading cannot reroll the score.
    factors = dict(
        condition=(float(state.get('condition', 85)) - 80) / 40,
        fatigue=-max(0, float(state.get('fatigue', 0)) - 15) / 65,
        morale=(float(state.get('morale', 75)) - 70) / 60,
        suitability=.25 if training.get('focus_aligned') else 0.,
        coaching=min(.3, max(0., float(training.get('coaching_support', 0))) * .08),
        daily_response=(roll(save_id, player['id'], day, 'training-performance') - .5) * 2.4,
    )
    rating = round(max(1., min(10., 6.8 + sum(factors.values()))), 1)
    return dict(rating=rating, participation=status, factors={k: round(v, 3) for k,v in factors.items()})


def record_training_rating(connection, save_id, player, state, day, training):
    result = evaluate_training(save_id, player, state, day, training)
    connection.execute('''INSERT OR IGNORE INTO player_training_ratings
        (save_id,player_id,training_date,team,rating,participation,focus,detail_json)
        VALUES (?,?,?,?,?,?,?,?)''', (save_id, player['id'], str(day), player['team'], result['rating'],
        result['participation'], training.get('focus') or '', json.dumps(result['factors'])))
    return result


def recent_ratings(connection, save_id, team, as_of):
    day = date.fromisoformat(str(as_of))
    start = (day - timedelta(days=13)).isoformat()
    split = (day - timedelta(days=6)).isoformat()
    groups = {}
    rows = connection.execute('''SELECT * FROM player_training_ratings
        WHERE save_id=? AND team=? AND training_date BETWEEN ? AND ? ORDER BY training_date DESC''',
        (save_id, team, start, day.isoformat()))
    for row in rows:
        groups.setdefault(row['player_id'], []).append(dict(row))
    result = {}
    for identifier, history in groups.items():
        current = [r['rating'] for r in history if r['training_date'] >= split and r['rating'] is not None]
        previous = [r['rating'] for r in history if r['training_date'] < split and r['rating'] is not None]
        average = round(sum(current) / len(current), 1) if current else None
        trend = round(average - sum(previous) / len(previous), 1) if current and previous else None
        result[identifier] = dict(average=average, days=len(current), trend=trend, history=history,
                                  latest=history[0]['rating'], status=history[0]['participation'])
    return result
