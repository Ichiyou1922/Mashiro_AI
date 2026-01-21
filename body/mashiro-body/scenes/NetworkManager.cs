using Godot;
using System;
using Vector2 = Godot.Vector2;
using System.Numerics;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Runtime.InteropServices;
using System.Threading.Tasks.Dataflow;


public partial class NetworkManager : Node
{
	// WebSocketPeerクラスのインスタンス化
	private WebSocketPeer _socket = new WebSocketPeer();

	// 接続先URL
	private string _url = "ws://127.0.0.1:8000/ws";

	// Audio関係
	private AudioEffectCapture _capture;
	private AudioStreamPlayer _player;  
	private AudioStreamGeneratorPlayback _playback;
	// Called when the node enters the scene tree for the first time.
	public override void _Ready()
	{
		GD.Print("Python Server へ接続...");
		Error err = _socket.ConnectToUrl(_url);

		if (err != Error.Ok)
		{
			GD.Print("接続エラーです");
		}
		
		// Recordバスのインデックスを取得
		int idx = AudioServer.GetBusIndex("Record");
		// RecordBusのEffectを取得(つまりRecord)
		_capture = (AudioEffectCapture)AudioServer.GetBusEffect(idx, 0);
		// 再生系
		_player = GetNode<AudioStreamPlayer>("../AudioStreamPlayer");
		_playback = (AudioStreamGeneratorPlayback)_player.GetStreamPlayback(); // データの挿入口を開通
	}
	
	// Called every frame. 'delta' is the elapsed time since the previous frame.
	public override void _Process(double delta)
	{
		_socket.Poll();

		WebSocketPeer.State state = _socket.GetReadyState();

		if (state == WebSocketPeer.State.Open)
		{
			while (_socket.GetAvailablePacketCount() > 0)
			{
				// 音声をbyteで受け取る
				byte[] bytedata = _socket.GetPacket();
				// Vec2[]に変換する
				ReadOnlySpan<Vector2> vectorSpan = MemoryMarshal.Cast<byte, Vector2>(new ReadOnlySpan<byte>(bytedata));
				Vector2[] vec2Data = vectorSpan.ToArray();

				if (_playback.GetFramesAvailable() > 0)
				{
					_playback.PushBuffer(vec2Data);
				}
				else
				{
					GD.Print("オーディオの再生に失敗しました");
				}
			}
			int framesAvailable = _capture.GetFramesAvailable();
				if (framesAvailable > 0)
				{
					Vector2[] audioFrames = _capture.GetBuffer(framesAvailable);
					float[] leftChannel = new float[audioFrames.Length];
					for (int i = 0; i < audioFrames.Length; i++)
					{
						leftChannel[i] = audioFrames[i].X;
					}
					byte[] byteData = new byte[leftChannel.Length * 4];
					System.Buffer.BlockCopy(leftChannel, 0, byteData, 0, byteData.Length);
					Error senderr = _socket.PutPacket(byteData);
					if (senderr != Error.Ok)
					{
						GD.Print("オーディオの送信に失敗しました");
					}
				}
		}
		else if (state == WebSocketPeer.State.Closed)
		{
			GD.Print("切断されました");
		}
		
	}
}
