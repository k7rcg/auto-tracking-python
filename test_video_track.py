import cv2
import time
from ultralytics import YOLO

# 1. Nanoモデルを読み込み（sからnへ変更し軽量化）
model = YOLO("yolov8n.pt")

# 2. 配置した動画ファイルの読み込み
video_path = "test_video.mp4"
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print(f"エラー: {video_path} を開けませんでした。パスや形式を確認してください。")
    exit()

# 動画の基本情報（幅、高さ、フレームレート）を取得
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)

# 3. 結果を保存するための動画書き込み準備 (MP4用フォーマット)
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter('track_result.mp4', fourcc, fps, (frame_width, frame_height))

print("動画の追跡解析を開始します。しばらくお待ちください...")
start_time = time.time()
frame_count = 0

# --- 【追加】動的制御のための初期設定パラメータ ---
# 1秒あたりの検知回数から、何フレームごとにYOLOを動かすか（間隔）を計算
# 初期値は「近く（1秒に2回）」を想定。動画のFPSに応じて自動計算。
fps_round = round(fps)
interval_near = max(1, fps_round // 2)  # 近く（1秒に2回用フレーム間隔）
interval_far = max(1, fps_round // 1)   # 遠く（1秒に1回用フレーム間隔）

current_interval = interval_near  # 現在の処理間隔（デフォルトは近く）
current_imgsz = 320               # 現在の入力解像度（近く：低解像度320、遠く：高解像度640）
annotated_frame = None            # スキップされたフレーム用に直近の描画結果を保持する変数

# 距離判定の閾値（バウンディングボックスの縦幅 px）
# 画面の縦解像度に対して、人が占める高さで「遠近」をだいたいで判定します
# ※動画の解像度や画角に合わせて数値を微調整してください
DISTANCE_THRESHOLD_PX = int(frame_height * 0.15) 
# --------------------------------------------------

# 4. 動画を1コマずつループ処理
while cap.isOpened():
    success, frame = cap.read() # 1コマ読み込み
    
    if not success:
        break # 動画が終了したらループを抜ける

    frame_count += 1

    # 【追加】指定したフレーム間隔（interval）のときだけYOLOの検知（track）を実行
    if frame_count == 1 or (frame_count % current_interval == 0):
        
        # 【変更点①】model() を model.track() に変更。さらに最軽量の "bytetrack.yaml" を指定。
        # 動的に変更された解像度（current_imgsz）で推論を実行
        results = model.track(source=frame, persist=True, imgsz=current_imgsz, conf=0.20, verbose=False, tracker="bytetrack.yaml")
        
        # 認識結果（枠・背番号ID）を画像に描き込む
        annotated_frame = results[0].plot()

        # 【変更点②】results[0].boxes.id が存在し、かつ中身が空でない（検出あり）場合の判定を厳密化
        if results[0].boxes.id is not None and len(results[0].boxes.id) > 0:
            track_ids = results[0].boxes.id.int().tolist()
            print(f"フレーム {frame_count}: 追跡中 ID -> {track_ids} (解像度:{current_imgsz}, 間隔:{current_interval}f)")
            
            # 【追加】検出された物体の大きさを調べて「遠近」を判定
            # boxes.xyxy から各物体の [左上のx, 左上のy, 右下のx, 右下のy] を取得
            boxes = results[0].boxes.xyxy.cpu().numpy()
            max_height = 0
            
            for box in boxes:
                box_h = box[3] - box[1] # 縦幅（高さ）を計算
                if box_h > max_height:
                    max_height = box_h # 画面内で一番大きく映っている（近い）人の高さを保持

            # 【追加】判定に基づき、次の検知パラメータ（解像度と検知頻度）を動的に切り替え
            if max_height < DISTANCE_THRESHOLD_PX:
                # 【遠く（10m目安）にいる場合】
                # 解像度を上げて（640）、捕捉頻度を下げる（1秒に1回）
                current_interval = interval_far
                current_imgsz = 640
            else:
                # 【近くにいる場合】
                # 解像度を下げて（320）、捕捉頻度を上げる（1秒に2回）
                current_interval = interval_near
                current_imgsz = 320
        else:
            print(f"フレーム {frame_count}: ターゲットを見失い中...")
            # 見失っているときは、発見しやすくするために一時的に「近く」の設定（高頻度）に戻す
            current_interval = interval_near
            current_imgsz = 640

    else:
        # 【追加】YOLOを動かさないスキップフレームの処理
        # 前回の検知結果（枠）が残っている場合は、現在の生フレームにそのまま上書き描画して動画の見た目を維持
        if annotated_frame is not None:
            # 前回の枠付き画像を使用（※完全な最新フレームへの枠重ね合わせではないですが処理を最軽量化できます）
            out.write(annotated_frame)
            continue
        else:
            annotated_frame = frame

    # 結果動画ファイルに1コマ書き込む
    out.write(annotated_frame)

end_time = time.time()
total_time = end_time - start_time
actual_fps = frame_count / total_time

print("\n--- 解析が完了しました ---")
print(f"処理した合計フレーム数: {frame_count} コマ")
print(f"解析にかかった時間: {total_time:.2f} 秒")
print(f"1秒あたりの処理速度: {actual_fps:.1f} 回 (FPS)")
print("結果動画を 'track_result.mp4' として保存しました。")

# 後片付け
cap.release()
out.release()
