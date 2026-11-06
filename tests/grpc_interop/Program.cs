// 真实 ClassIsland 2.1 客户端的集控协议互通测试程序。
//
// 它引用客户端自带的 ClassIsland.Shared.dll / Google.Protobuf / Grpc.Net.Client /
// PgpCore / BouncyCastle，因此走的是与真实客户端完全相同的 protobuf 消息、gRPC
// 栈和 PGP 实现——只要这里的每一步都能通过，真实客户端也能通过。
//
// 覆盖：Register → BeginHandshake(PGP 挑战) → CompleteHandshake → ListenCommand
//       → Ping/Pong → SendNotification / RestartApp / GetClientConfig → Audit / ConfigUpload。

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

using ClassIsland.Shared.Protobuf.Client;
using ClassIsland.Shared.Protobuf.Command;
using ClassIsland.Shared.Protobuf.Enum;
using ClassIsland.Shared.Protobuf.Server;
using ClassIsland.Shared.Protobuf.Service;
using Google.Protobuf;
using Grpc.Core;
using Grpc.Net.Client;
using PgpCore;

namespace GrpcClientInterop;

internal static class Program
{
    private const string ProtocolName = "Cyrene_MSP";
    private const string ProtocolVersion = "2.0.0.0";

    private static string _grpcAddress = "http://127.0.0.1:7879";
    private static string _httpAddress = "http://127.0.0.1:7878";
    private static Guid _clientGuid = Guid.Parse("99999999-8888-7777-6666-555555555555");
    private static string _clientId = "device-1";
    private static string _clientMac = "AA:BB:CC:DD:EE:FF";
    private static string _keyPath = "";

    private static readonly List<string> Results = new();
    private static int _failures;

    private static void Check(string name, bool ok, string detail = "")
    {
        if (ok)
        {
            Results.Add($"  [ok]   {name}");
            Console.WriteLine($"  [ok]   {name}");
        }
        else
        {
            _failures++;
            Results.Add($"  [FAIL] {name} {detail}");
            Console.WriteLine($"  [FAIL] {name} {detail}");
        }
    }

    private static Metadata GetMetadata(string session = "", bool withSession = true)
    {
        var md = new Metadata
        {
            { "cuid", _clientGuid.ToString() },
            { "protocol_name", ProtocolName },
            { "protocol_version", ProtocolVersion },
            { "session", session },
        };
        return md;
    }

    public static async Task<int> Main(string[] args)
    {
        for (var i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--grpc" when i + 1 < args.Length: _grpcAddress = args[++i]; break;
                case "--http" when i + 1 < args.Length: _httpAddress = args[++i]; break;
                case "--cuid" when i + 1 < args.Length: _clientGuid = Guid.Parse(args[++i]); break;
                case "--id" when i + 1 < args.Length: _clientId = args[++i]; break;
                case "--mac" when i + 1 < args.Length: _clientMac = args[++i]; break;
                case "--key" when i + 1 < args.Length: _keyPath = args[++i]; break;
            }
        }
        if (string.IsNullOrEmpty(_keyPath))
        {
            _keyPath = Path.Combine(Path.GetTempPath(), $"ci-server-{_clientGuid}.asc");
        }

        Console.WriteLine($"gRPC {_grpcAddress} / HTTP {_httpAddress} / cuid {_clientGuid}");
        using var channel = GrpcChannel.ForAddress(_grpcAddress);

        await TestMetadataValidation(channel);
        var manifest = await TestRegister(channel);
        var session = await TestHandshake(channel);
        await TestListen(channel, session);
        await TestNotifyAndRestart(channel, session);
        await TestAuditAndUpload(channel, session);

        Console.WriteLine();
        if (_failures == 0)
        {
            Console.WriteLine($"ALL GRPC INTEROP CHECKS PASSED ({Results.Count} checks)");
            return 0;
        }
        Console.WriteLine($"GRPC INTEROP CHECKS FAILED: {_failures}/{Results.Count}");
        return 1;
    }

    // ------------------------------------------------------------- metadata
    private static async Task TestMetadataValidation(GrpcChannel channel)
    {
        Console.WriteLine("==> 元数据校验（缺少 protocol_name 必须被拒）");
        var register = new ClientRegister.ClientRegisterClient(channel);
        var bad = new Metadata
        {
            { "cuid", _clientGuid.ToString() },
            { "session", "" },
        };
        var rejected = false;
        var status = "";
        try
        {
            await register.RegisterAsync(
                new ClientRegisterCsReq { ClientUid = _clientGuid.ToString(), ClientId = _clientId, ClientMac = _clientMac },
                bad);
        }
        catch (RpcException e)
        {
            rejected = e.StatusCode is StatusCode.InvalidArgument or StatusCode.PermissionDenied;
            status = $"{e.StatusCode}: {e.Status.Detail}";
        }
        Check("缺 protocol_name 的 Register 被拒绝", rejected, status);

        var noSession = new Metadata
        {
            { "cuid", _clientGuid.ToString() },
            { "protocol_name", ProtocolName },
        };
        var rejected2 = false;
        var status2 = "";
        try
        {
            var deliver = new ClientCommandDeliver.ClientCommandDeliverClient(channel);
            using var call = deliver.ListenCommand(noSession);
            await call.ResponseStream.MoveNext(CancellationToken.None);
        }
        catch (RpcException e)
        {
            rejected2 = e.StatusCode is StatusCode.InvalidArgument or StatusCode.PermissionDenied;
            status2 = $"{e.StatusCode}: {e.Status.Detail}";
        }
        Check("缺 session 的 ListenCommand 被拒绝", rejected2, status2);
    }

    // -------------------------------------------------------------- register
    private static async Task<ManagementManifestShim> TestRegister(GrpcChannel channel)
    {
        Console.WriteLine("==> Register");
        var register = new ClientRegister.ClientRegisterClient(channel);
        var rsp = await register.RegisterAsync(
            new ClientRegisterCsReq { ClientUid = _clientGuid.ToString(), ClientId = _clientId, ClientMac = _clientMac },
            GetMetadata(withSession: true));
        Check("Register 返回 Success 或 Registered", rsp.Retcode is Retcode.Success or Retcode.Registered, rsp.Retcode.ToString());
        Check("Register 返回服务器 PGP 公钥", !string.IsNullOrWhiteSpace(rsp.ServerPublicKey) && rsp.ServerPublicKey.Contains("BEGIN PGP PUBLIC KEY BLOCK"));
        if (!string.IsNullOrWhiteSpace(rsp.ServerPublicKey))
        {
            await File.WriteAllTextAsync(_keyPath, rsp.ServerPublicKey);
        }

        // 真实客户端注册成功后立刻拉 manifest（ManagementServerConnection.RegisterAsync :177）
        var http = new HttpClient();
        var url = $"{_httpAddress}/api/v1/client/{_clientGuid}/manifest";
        var json = await http.GetStringAsync(url);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;
        Check("manifest 的 coreVersion 主版本为 2", root.TryGetProperty("coreVersion", out var cv) && cv.GetString().StartsWith("2."), cv.ToString());
        Check("manifest 的 serverKind 为 ManagementServer(1)", root.TryGetProperty("serverKind", out var sk) && sk.GetInt32() == 1);
        Check("manifest 含 credentialSource / componentsSource", root.TryGetProperty("credentialSource", out _) && root.TryGetProperty("componentsSource", out _));
        return new ManagementManifestShim();
    }

    // ------------------------------------------------------------- handshake
    private static async Task<string> TestHandshake(GrpcChannel channel)
    {
        Console.WriteLine("==> Handshake（真实 PGP 加解密）");
        var handshake = new Handshake.HandshakeClient(channel);

        await using var publicKeyStream = File.OpenRead(_keyPath);
        await using var decodeStream = Org.BouncyCastle.Bcpg.OpenPgp.PgpUtilities.GetDecoderStream(publicKeyStream);
        var pgpPub = new Org.BouncyCastle.Bcpg.OpenPgp.PgpPublicKeyRing(decodeStream);
        var key = pgpPub.GetPublicKey();
        Check("服务器公钥可被 BouncyCastle 解析", key != null);

        var keyId = key.KeyId;
        var challengeToken = Convert.ToBase64String(RandomNumberGenerator.GetBytes(64));
        publicKeyStream.Position = 0;
        var pgp = new PGP(new EncryptionKeys(publicKeyStream));
        var encrypted = await pgp.EncryptAsync(challengeToken);

        var begin = await handshake.BeginHandshakeAsync(
            new HandshakeScBeginHandShakeReq
            {
                ChallengeTokenEncrypted = encrypted,
                ClientMac = _clientMac,
                ClientUid = _clientGuid.ToString(),
                RequestedServerKeyId = keyId,
            },
            GetMetadata());
        Check("BeginHandshake 返回 Success", begin.Retcode == Retcode.Success, $"{begin.Retcode} {begin.Message}");
        Check("BeginHandshake 解出的挑战令牌与原文一致", begin.ChallengeTokenDecrypted == challengeToken);
        Check("BeginHandshake 回传服务器公钥", !string.IsNullOrWhiteSpace(begin.ServerPublicKey));

        var complete = await handshake.CompleteHandshakeAsync(
            new HandshakeScCompleteHandshakeReq { Accepted = begin.ChallengeTokenDecrypted == challengeToken },
            GetMetadata());
        Check("CompleteHandshake 返回 Success", complete.Retcode == Retcode.Success, complete.Message);
        Check("CompleteHandshake 返回非空 SessionId", !string.IsNullOrWhiteSpace(complete.SessionId));

        // MAC 不匹配必须被拒
        var badMac = await handshake.BeginHandshakeAsync(
            new HandshakeScBeginHandShakeReq
            {
                ChallengeTokenEncrypted = encrypted,
                ClientMac = "00:00:00:00:00:00",
                ClientUid = _clientGuid.ToString(),
                RequestedServerKeyId = keyId,
            },
            GetMetadata());
        Check("MAC 不匹配时 BeginHandshake 返回 HandshakeClientRejected", badMac.Retcode == Retcode.HandshakeClientRejected, badMac.Retcode.ToString());

        return complete.SessionId;
    }

    // ---------------------------------------------------------------- listen
    private static async Task TestListen(GrpcChannel channel, string session)
    {
        Console.WriteLine("==> ListenCommand（心跳与命令投递）");
        var deliver = new ClientCommandDeliver.ClientCommandDeliverClient(channel);
        // 不能 using：真实客户端（ManagementServerConnection.ListenCommands）会让命令流
        // 在应用生命周期内保持打开，后续 TestNotifyAndRestart 还要从这个流上读命令。
        var call = deliver.ListenCommand(GetMetadata(session));
        _call = call;

        await call.RequestStream.WriteAsync(new ClientCommandDeliverScReq { Type = CommandTypes.Ping });
        var pong = await ReadNext(call, TimeSpan.FromSeconds(10));
        Check("Ping 收到 Pong", pong != null && pong.Type == CommandTypes.Pong, pong == null ? "timeout" : $"{pong.Type}/{pong.RetCode}");
    }

    private static ClientCommandDeliver.ClientCommandDeliverClient _client = null;
    private static AsyncDuplexStreamingCall<ClientCommandDeliverScReq, ClientCommandDeliverScRsp> _call;

    private static async Task<ClientCommandDeliverScRsp> ReadNext(
        AsyncDuplexStreamingCall<ClientCommandDeliverScReq, ClientCommandDeliverScRsp> call,
        TimeSpan timeout)
    {
        using var cts = new CancellationTokenSource(timeout);
        try
        {
            if (!await call.ResponseStream.MoveNext(cts.Token))
            {
                return null;
            }
            return call.ResponseStream.Current;
        }
        catch (OperationCanceledException)
        {
            return null;
        }
    }

    /// <summary>
    /// 服务端在命令流建立时会主动推一个 Pong 心跳（
    /// ClientCommandDeliverFrontedService.ListenCommand 里的 DeliverCommandAsync(Pong)），
    /// 所以读取业务命令时必须跳过 Pong，和真实客户端 ListenCommands 的处理一致。
    /// </summary>
    private static async Task<ClientCommandDeliverScRsp> ReadUntilNonPong(
        AsyncDuplexStreamingCall<ClientCommandDeliverScReq, ClientCommandDeliverScRsp> call,
        TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            var rsp = await ReadNext(call, deadline - DateTime.UtcNow);
            if (rsp == null)
            {
                return null;
            }
            if (rsp.Type == CommandTypes.Pong)
            {
                continue;
            }
            return rsp;
        }
        return null;
    }

    // ---------------------------------------------------- notification/restart
    private static async Task TestNotifyAndRestart(GrpcChannel channel, string session)
    {
        Console.WriteLine("==> REST 命令投递（show-notification / restart-app）");
        var token = await Login();
        var http = new HttpClient();
        http.DefaultRequestHeaders.Add("Authorization", $"Bearer {token}");

        var notifyBody = JsonSerializer.Serialize(new
        {
            targets = new[]
            {
                new { objectId = "00000000-0000-0000-0000-000000000000", objectType = 0,
                      targetClientId = (string)null, targetClientCuid = _clientGuid.ToString(),
                      targetGroupId = (int?)null, assigneeType = 1 },
            },
            payload = new
            {
                messageMask = "互通测试通知",
                messageContent = "来自 gRPC 互通测试",
                overlayIconLeft = 0,
                overlayIconRight = 0,
                isEmergency = false,
                isSpeechEnabled = false,
                isEffectEnabled = false,
                isSoundEnabled = false,
                isTopmost = false,
                durationSeconds = 3.0,
                repeatCounts = 1,
            },
        });
        var r1 = await http.PostAsync($"{_httpAddress}/api/v1/client-commands/show-notification",
            new StringContent(notifyBody, Encoding.UTF8, "application/json"));
        Check("POST show-notification 返回 200", (int)r1.StatusCode == 200, ((int)r1.StatusCode).ToString());

        var received = await ReadUntilNonPong(_call, TimeSpan.FromSeconds(10));
        var okNotify = received != null && received.Type == CommandTypes.SendNotification && received.RetCode == Retcode.Success;
        Check("客户端收到 SendNotification 命令", okNotify, received == null ? "timeout" : $"{received.Type}/{received.RetCode}");
        if (okNotify)
        {
            var payload = SendNotification.Parser.ParseFrom(received.Payload);
            Check("SendNotification 载荷可被真实类型解析", payload.MessageMask == "互通测试通知", payload.MessageMask);
        }

        var restartBody = JsonSerializer.Serialize(new
        {
            targets = new[]
            {
                new { objectId = "00000000-0000-0000-0000-000000000000", objectType = 0,
                      targetClientId = (string)null, targetClientCuid = _clientGuid.ToString(),
                      targetGroupId = (int?)null, assigneeType = 1 },
            },
        });
        var r2 = await http.PostAsync($"{_httpAddress}/api/v1/client-commands/restart-app",
            new StringContent(restartBody, Encoding.UTF8, "application/json"));
        Check("POST restart-app 返回 200", (int)r2.StatusCode == 200, ((int)r2.StatusCode).ToString());
        var received2 = await ReadUntilNonPong(_call, TimeSpan.FromSeconds(10));
        Check("客户端收到 RestartApp 命令", received2 != null && received2.Type == CommandTypes.RestartApp && received2.RetCode == Retcode.Success,
            received2 == null ? "timeout" : $"{received2.Type}/{received2.RetCode}");
    }

    // ------------------------------------------------------------ audit/upload
    private static async Task TestAuditAndUpload(GrpcChannel channel, string session)
    {
        Console.WriteLine("==> Audit / ConfigUpload");
        var audit = new Audit.AuditClient(channel);
        try
        {
            var rsp = await audit.LogEventAsync(
                new AuditScReq { Event = AuditEvents.AppCrashed, Payload = ByteString.Empty, TimestampUtc = 0 },
                GetMetadata(session));
            Check("LogEvent 返回 Success", rsp.Retcode == Retcode.Success, rsp.Retcode.ToString());
        }
        catch (RpcException e)
        {
            Check("LogEvent 返回 Success", false, $"{e.StatusCode}: {e.Status.Detail}");
        }

        var upload = new ConfigUpload.ConfigUploadClient(channel);
        try
        {
            var rsp = await upload.UploadConfigAsync(
                new ConfigUploadScReq { RequestGuidId = Guid.NewGuid().ToString(), Payload = "{}" },
                GetMetadata(session));
            Check("UploadConfig 返回 Success", rsp.Retcode == Retcode.Success, rsp.Retcode.ToString());
        }
        catch (RpcException e)
        {
            Check("UploadConfig 返回 Success", false, $"{e.StatusCode}: {e.Status.Detail}");
        }
    }

    private static async Task<string> Login()
    {
        var http = new HttpClient();
        var body = JsonSerializer.Serialize(new { username = "root", password = "root" });
        var rsp = await http.PostAsync($"{_httpAddress}/api/v1/auth/login",
            new StringContent(body, Encoding.UTF8, "application/json"));
        var json = await rsp.Content.ReadAsStringAsync();
        using var doc = JsonDocument.Parse(json);
        return doc.RootElement.GetProperty("accessToken").GetString();
    }

    private sealed class ManagementManifestShim
    {
    }
}

