# ニャンコ大運動会 オンライン v0.11 開発版

## 今回の実装
- 格闘の必殺技・パンチ命中時にキャラを座標ジャンプさせず、サーバー側で速度(vx/vy)を保持。毎フレーム減速する吹っ飛びへ変更。
- 張り手・旋風脚の吹っ飛び速度調整。台の四辺を足元が越えた瞬間に場外判定、直前に吹っ飛ばしたキャラへ+3点。HPゼロはKOで-3点。
- フロント側も顔の向き・吹っ飛び軌跡・攻撃/KO/場外エフェクトを同期。
- 既存の5区間レース・サーバー共通リズム譜面・ロビー・3競技進行は維持。

## 現状
まだ1人用と同等のゲーム性の完全移植ではありません。Renderへの更新は不要です。
サーバー起動: `pip install -r requirements.txt` → `python server.py`

## v0.12 race collision / items improvements
- Hazard-specific server effects: banana slipping, puddle slowing, box/hurdle impact.
- Short race collision invulnerability prevents repeated edge-hit damage.
- Pan projectiles no longer cause immediate duplicate damage before projectile travels.
- CPU approaches shared beneficial items; collision effect messages are displayed over racers.
- Race HUD now shows HP, skateboard remaining time and weapon state.
- Existing online lobby, three-sport tournament and battle remain intact.

Development build only. Not equivalent to all features in the original offline race.


## Ver.0.13 差分（開発版）
- レースのパンチ方向を移動方向に連動。後方にも向いて攻撃可能。
- パンチの一度だけの判定・無敵時間・距離によるノックバック。
- CPUも近距離で一定間隔のパンチを使用。
- レースHPゼロでは2.4秒ダウンし、HP65で復帰、2.2秒の無敵。
- 投げるフライパンは向きに合わせて前後に飛ぶ。
- 画面でDOWNと復帰状態を表示。
- 開発版：原作の完全移植ではないためRenderには未アップロード推奨。
