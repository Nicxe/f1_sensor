# Changelog

## Unreleased
- Resolve race control stream URL from official index files for improved reliability.
- Poll using HTTP range requests, reducing bandwidth usage by about 90%.
- Session detection now uses real-time status across all meetings and includes TrackStatus feed for accurate flags.
- SignalR live-feed + fallback.
- Fix incorrect signalrcore-async version in manifest.
