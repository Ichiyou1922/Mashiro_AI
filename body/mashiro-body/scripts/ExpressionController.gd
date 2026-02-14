extends GDCubismEffectCustom

class_name ExpressionController

var current_emotion = "neutral"
var param_dict = {}
var _model: GDCubismUserModel

var _mouth_open_y: float = 0.0
var _target_params: Dictionary = {}
const SMOOTH_WEIGHT: float = 0.1

# 制御対象のパラメータとデフォルト値
const DEFAULT_PARAMS = {
	"ParamEyeLSmile": 0.0,
	"ParamEyeRSmile": 0.0,
	"ParamMouthForm": 1.0,
	"ParamCheek": 0.0,
	"ParamBrowLY": 0.0,
	"ParamBrowRY": 0.0,
	"ParamBrowLAngle": 0.0,
	"ParamBrowRAngle": 0.0,
	"ParamEyeLOpen": 1.0,
	"ParamEyeROpen": 1.0,
	"ParamMouthOpenY": 0.0
}

func _ready():
	# 初期ターゲット設定
	for key in DEFAULT_PARAMS:
		_target_params[key] = DEFAULT_PARAMS[key]
		
	# シグナル接続
	cubism_init.connect(_on_cubism_init)
	cubism_epilogue.connect(_on_cubism_epilogue)

func _on_cubism_init(model: GDCubismUserModel):
	_model = model
	var params = model.get_parameters()
	for p in params:
		param_dict[p.id] = p
	print("ExpressionController: Parameters initialized. Count: ", params.size())

func _on_cubism_epilogue(_model: GDCubismUserModel, _delta: float):
	# モーション再生などで上書きされた後に表情パラメータを適用する
	apply_expression_parameters()

func set_emotion(emotion_name: String):
	if current_emotion != emotion_name:
		current_emotion = emotion_name
		_update_targets(emotion_name)
		print("ExpressionController: Emotion set to ", emotion_name)

func set_mouth_open(value: float):
	_mouth_open_y = value
	if _target_params.has("ParamMouthOpenY"):
		_target_params["ParamMouthOpenY"] = value

func _update_targets(emotion: String):
	# まずデフォルト値にリセット
	for key in DEFAULT_PARAMS:
		if key == "ParamMouthOpenY": continue # 口パクは別管理
		_target_params[key] = DEFAULT_PARAMS[key]

	# 感情ごとの上書き
	match emotion:
		"happy":
			_target_params["ParamEyeLSmile"] = 1.0
			_target_params["ParamEyeRSmile"] = 1.0
			_target_params["ParamMouthForm"] = 1.0
			_target_params["ParamCheek"] = 0.5
		"sad":
			_target_params["ParamBrowLY"] = -0.5
			_target_params["ParamBrowRY"] = -0.5
			_target_params["ParamMouthForm"] = -0.5
			_target_params["ParamEyeLOpen"] = 0.8
			_target_params["ParamEyeROpen"] = 0.8
		"angry":
			_target_params["ParamBrowLY"] = -0.5
			_target_params["ParamBrowRY"] = -0.5
			_target_params["ParamBrowLAngle"] = 0.5 # つり眉
			_target_params["ParamBrowRAngle"] = 0.5
			_target_params["ParamMouthForm"] = -0.5
		"surprised":
			_target_params["ParamEyeLOpen"] = 1.2 # 見開き
			_target_params["ParamEyeROpen"] = 1.2
			_target_params["ParamBrowLY"] = 0.5
			_target_params["ParamBrowRY"] = 0.5
			_target_params["ParamMouthForm"] = -0.3
		"shy":
			_target_params["ParamCheek"] = 1.0
			_target_params["ParamEyeLOpen"] = 0.9
			_target_params["ParamEyeROpen"] = 0.9
		"sleepy":
			_target_params["ParamEyeLOpen"] = 0.5
			_target_params["ParamEyeROpen"] = 0.5
			_target_params["ParamMouthForm"] = 0.0
		"wink":
			_target_params["ParamEyeLOpen"] = 0.0
			_target_params["ParamEyeROpen"] = 1.0
			_target_params["ParamMouthForm"] = 1.0
		"neutral":
			pass # デフォルトのまま

func apply_expression_parameters():
	if param_dict.is_empty(): return
	
	# 現在値をターゲットに滑らかに近づける
	for pid in _target_params:
		if param_dict.has(pid):
			var current: float = param_dict[pid].value
			var target: float = _target_params[pid]
			
			# 口パクは即座に反映させたい場合はlerpしない、あるいは高速にする
			if pid == "ParamMouthOpenY":
				param_dict[pid].value = target
			else:
				# 線形補間
				param_dict[pid].value = lerp(current, target, SMOOTH_WEIGHT)
