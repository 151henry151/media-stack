-- Add OGG Vorbis transcoder (gapless playback) to Airsonic
-- Run when Airsonic is STOPPED via airsonic-add-ogg-transcoder.sh

INSERT INTO TRANSCODING (ID, NAME, SOURCE_FORMATS, TARGET_FORMAT, STEP1, STEP2, STEP3, DEFAULT_ACTIVE) VALUES (5, 'ffmpeg - OGG (gapless)', '*', 'ogg', 'ffmpeg -re -i %s -map 0:a:0 -c:a libvorbis -q:a 4 -f ogg -', NULL, NULL, TRUE);

INSERT INTO PLAYER_TRANSCODING (PLAYER_ID, TRANSCODING_ID) SELECT P.ID, 5 FROM PLAYER P WHERE P.TYPE LIKE '%Substreamer%' AND NOT EXISTS (SELECT 1 FROM PLAYER_TRANSCODING PT WHERE PT.PLAYER_ID = P.ID AND PT.TRANSCODING_ID = 5);

COMMIT;
