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

	// Called when the node enters the scene tree for the first time.
	public override void _Ready()
	{
		GD.Print("Python Server へ接続...");
		Error err = _socket.ConnectToUrl(_url);

		if (err != Error.Ok)
		{
			GD.Print("接続エラーです");
		}
	
	// Called every frame. 'delta' is the elapsed time since the previous frame.
	public override void _Process(double delta)
	{
		_socket.Poll();

		WebSocketPeer.State state = _socket.GetReadyState();

		if (state == WebSocketPeer.State.Open)
		{
			
		}
		else if (state == WebSocketPeer.State.Closed)
		{
			GD.Print("切断されました");
		}
		
	}
}
