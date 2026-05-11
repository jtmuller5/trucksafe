import 'dart:io';
import 'dart:typed_data';

import 'package:image/image.dart' as img;

/// Resize the captured image to roughly `maxEdge` on its long side and
/// JPEG-encode it at `quality`. Returns the encoded bytes.
///
/// This is intentionally lossy: Gemma 4 E4B's vision tower works fine
/// well under 1024px on the long edge and the size cut speeds up inference.
Future<Uint8List> preprocessJpeg(
  File source, {
  int maxEdge = 896,
  int quality = 85,
}) async {
  final bytes = await source.readAsBytes();
  final decoded = img.decodeImage(bytes);
  if (decoded == null) {
    throw const FormatException('Could not decode captured image');
  }
  final resized = decoded.width >= decoded.height
      ? img.copyResize(decoded, width: maxEdge, interpolation: img.Interpolation.linear)
      : img.copyResize(decoded, height: maxEdge, interpolation: img.Interpolation.linear);
  return Uint8List.fromList(img.encodeJpg(resized, quality: quality));
}
