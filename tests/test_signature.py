from mexc_bot.mexc.auth import sign_params

def test_signature_shape():
    secret = "test_secret"
    params = {"timestamp": 1, "recvWindow": 5000, "symbol": "XRPUSDT"}
    sig = sign_params(secret, params)
    assert len(sig) == 64
    assert sig == sig.lower()
