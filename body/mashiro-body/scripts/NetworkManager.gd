extends Node

@export var _url = "ws://127.0.0.1:8000/ws/godot"
var ws = WebSocketPeer.new()
var model: GDCubismUserModel
var param_dict = {}
var current_emotion = "neutral"
var time_accum = 0.0

var current_ai_state = "idle"
var last_message_time = 0
const MOUTH_TIMEOUT_MS = 3000 # 3000ms
# const SPEAK_START_DELAY_MS = 1000 # 音声再生遅延に合わせるための待機時間
const EMOTION_RESET_DURATION_MS = 5000 # 感情表示時間（ミリ秒）
var speak_start_time = 0
var emotion_reset_timer = 0

func _ready():
	var err = ws.connect_to_url(_url)
	if err == OK:
		print("Connecting to Python Server")
		model = get_node("../GDCubismUserModel")
		var params = model.get_parameters()
		for p in params:
			param_dict[p.id] = p

	# Hiyoriモデルに切り替え
		
		# モデルの位置とサイズを調整 (Hiyori用)
		# Hiyoriは標準的なサイズなので、画面中央に配置
		var viewport_rect = get_viewport().get_visible_rect()
		model.position = Vector2(viewport_rect.size.x * 0.5 + 100, viewport_rect.size.y * 0.8 + 400)
		model.scale = Vector2(0.4, 0.4)
		print("Model position adjusted to: ", model.position)

		# get_viewport().transparent_bg = false
		DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_BORDERLESS, true)
		# RenderingServer.set_default_clear_color(Color(0, 1, 0, 1))
		
		# 表情コントローラーを追加
		_setup_expression_controller()

	else:
		push_error("Unable to connect.")
		set_process(false)

var expression_controller: Node = null

func _setup_expression_controller():
	# ExpressionController (GDCubismEffectCustom) を動的に追加
	expression_controller = preload("res://scripts/ExpressionController.gd").new()
	model.add_child(expression_controller)
	print("ExpressionController added to model")

func _process(_delta):
	ws.poll()
	var state = ws.get_ready_state()
	
	if state == WebSocketPeer.STATE_OPEN:
		while ws.get_available_packet_count() > 0:
			var message = ws.get_packet().get_string_from_utf8()
			# print("Received: ", message)
			var doc = JSON.parse_string(message)
			var type = doc["type"]

			# メッセージ受信時刻を更新
			last_message_time = Time.get_ticks_msec()

			if type == "text_response":
				pass
			
			elif type == "state":
				current_ai_state = doc["payload"]["state"]
				pass

			elif type == "volume":
				var raw_volume = doc["payload"]["volume"]
				# 正規化: RMS値(0 ~ 32768) -> 0.0 ~ 1.0
				# 閾値は実際の音声を見て調整
				var normalized = clamp(raw_volume / 3000.0, 0.0, 1.0)
				# print(normalized)
				if expression_controller:
					expression_controller.set_mouth_open(normalized)

			elif type == "emotion":
				var emotion = doc["payload"]["emotion"]
				if current_emotion != emotion:
					current_emotion = emotion
					if expression_controller:
						expression_controller.set_emotion(current_emotion)
					print("Emotion changed to: ", emotion)
					
					# 感情変更から一定時間後にニュートラルに戻すタイマーを設定
					emotion_reset_timer = Time.get_ticks_msec() + EMOTION_RESET_DURATION_MS

		# 状態ごとの継続処理 (毎フレーム実行)
		
		# 感情リセットタイマーの監視
		if emotion_reset_timer > 0 and Time.get_ticks_msec() > emotion_reset_timer:
			emotion_reset_timer = 0
			if current_emotion != "neutral":
				current_emotion = "neutral"
				if expression_controller:
					expression_controller.set_emotion("neutral")
				print("Emotion reset timer: Reset emotion to neutral")

		if current_ai_state == "idle":
			if expression_controller:
				expression_controller.set_mouth_open(0.0)

		elif current_ai_state == "sleep":
			pass

		elif current_ai_state == "thinking":
			if expression_controller:
				expression_controller.set_mouth_open(0.0)
		elif current_ai_state == "speaking":
			pass
		else:
			if expression_controller:
				expression_controller.set_mouth_open(0.0)
					
	elif state == WebSocketPeer.STATE_CLOSING:
		pass
	
	elif state == WebSocketPeer.STATE_CLOSED:
		var code = ws.get_close_code()
		print("WebSocket closed with code: %d. Clean: %s" % [code, code != -1])
		set_process(false)
