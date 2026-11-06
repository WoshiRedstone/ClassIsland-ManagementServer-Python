using System;
using System.IO;
using System.Threading.Tasks;
using PgpCore;
using Org.BouncyCastle.Bcpg.OpenPgp;

class Probe
{
    static async Task Main()
    {
        var path = @"C:\man\_srv_pub.asc";
        await using var pkStream = File.OpenRead(path);
        await using var decode = PgpUtilities.GetDecoderStream(pkStream);
        var ring = new PgpPublicKeyRing(decode);
        var key = ring.GetPublicKey();
        Console.WriteLine($"key id={key.KeyId} alg={key.Algorithm} bits={key.BitStrength}");
        pkStream.Position = 0;
        var pgp = new PGP(new EncryptionKeys(pkStream));
        var token = Convert.ToBase64String(System.Security.Cryptography.RandomNumberGenerator.GetBytes(64));
        var enc = await pgp.EncryptAsync(token);
        Console.WriteLine($"enc len={enc.Length}");
        Console.WriteLine(enc.Substring(0, Math.Min(120, enc.Length)));
        Console.WriteLine("...TAIL...");
        Console.WriteLine(enc.Substring(Math.Max(0, enc.Length - 120)));
        File.WriteAllText(@"C:\man\_cs_enc.txt", enc);
        File.WriteAllText(@"C:\man\_cs_token.txt", token);
    }
}
