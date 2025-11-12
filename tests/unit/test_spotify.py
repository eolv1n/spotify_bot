from bot import extract_spotify_id

def test_extract_spotify_id_from_track_url():
    url = "https://open.spotify.com/track/5KawlOMHjWeUjQtnuRs22c"
    result = extract_spotify_id(url)
    assert result == "5KawlOMHjWeUjQtnuRs22c"
