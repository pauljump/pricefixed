// OCR image-only DOB/BIS PDFs locally with Poppler and Apple Vision.
//
// This is a review aid, not a unit importer. OCR text is never canonical
// evidence by itself: retain the source PDF and review the scanned document's
// exact premise, BBL, and unit-bearing language before accepting anything.
import AppKit
import Foundation
import Vision

struct OCRLine {
    let text: String
    let box: CGRect
}

func usage() -> Never {
    fputs("usage: ocr_dob_pdf_macos.swift input.pdf [output.txt] [scale]\n", stderr)
    exit(2)
}

func findPdftoppm() -> String? {
    for path in ["/opt/homebrew/bin/pdftoppm", "/usr/local/bin/pdftoppm", "/usr/bin/pdftoppm"] {
        if FileManager.default.isExecutableFile(atPath: path) { return path }
    }
    return nil
}

let arguments = CommandLine.arguments
guard arguments.count >= 2 && arguments.count <= 4 else { usage() }
let inputURL = URL(fileURLWithPath: arguments[1])
let outputURL = arguments.count >= 3 ? URL(fileURLWithPath: arguments[2]) : nil
let scale = arguments.count >= 4 ? CGFloat(Double(arguments[3]) ?? 2.0) : 2.0

guard let pdftoppm = findPdftoppm() else {
    fputs("pdftoppm not found; install Poppler or render the PDF to PNG first\n", stderr)
    exit(1)
}

let temporaryDirectory = FileManager.default.temporaryDirectory
    .appendingPathComponent("pricefixed-dob-ocr-\(UUID().uuidString)")
let prefix = temporaryDirectory.appendingPathComponent("page").path
do {
    try FileManager.default.createDirectory(at: temporaryDirectory, withIntermediateDirectories: true)
    let renderer = Process()
    renderer.executableURL = URL(fileURLWithPath: pdftoppm)
    renderer.arguments = ["-png", "-r", String(max(72, Int((scale * 100).rounded()))), inputURL.path, prefix]
    try renderer.run()
    renderer.waitUntilExit()
    guard renderer.terminationStatus == 0 else {
        fputs("pdftoppm failed for \(inputURL.path)\n", stderr)
        exit(1)
    }
} catch {
    fputs("could not render PDF: \(error)\n", stderr)
    exit(1)
}
defer { try? FileManager.default.removeItem(at: temporaryDirectory) }

let pageURLs: [URL]
do {
    pageURLs = try FileManager.default.contentsOfDirectory(
        at: temporaryDirectory, includingPropertiesForKeys: nil
    ).filter { $0.pathExtension.lowercased() == "png" }.sorted { $0.path < $1.path }
} catch {
    fputs("could not list rendered pages: \(error)\n", stderr)
    exit(1)
}
guard !pageURLs.isEmpty else {
    fputs("PDF rendered no pages: \(inputURL.path)\n", stderr)
    exit(1)
}

var output = ""
for (pageIndex, pageURL) in pageURLs.enumerated() {
    guard let image = NSImage(contentsOf: pageURL) else {
        fputs("could not load rendered page \(pageIndex + 1)\n", stderr)
        continue
    }
    var proposed = NSRect(origin: .zero, size: image.size)
    guard let cgImage = image.cgImage(forProposedRect: &proposed, context: nil, hints: nil) else {
        fputs("could not create image for page \(pageIndex + 1)\n", stderr)
        continue
    }

    var lines: [OCRLine] = []
    let request = VNRecognizeTextRequest { request, error in
        if let error = error {
            fputs("OCR page \(pageIndex + 1) failed: \(error)\n", stderr)
            return
        }
        lines = (request.results as? [VNRecognizedTextObservation] ?? []).compactMap { observation in
            guard let candidate = observation.topCandidates(1).first else { return nil }
            return OCRLine(text: candidate.string, box: observation.boundingBox)
        }
    }
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-US"]
    do {
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
    } catch {
        fputs("OCR page \(pageIndex + 1) failed: \(error)\n", stderr)
    }
    lines.sort {
        if abs($0.box.midY - $1.box.midY) > 0.012 {
            return $0.box.midY > $1.box.midY
        }
        return $0.box.minX < $1.box.minX
    }

    output += "=== page \(pageIndex + 1) ===\n"
    output += lines.map(\.text).joined(separator: "\n")
    output += "\n"
}

if let outputURL = outputURL {
    do {
        try output.write(to: outputURL, atomically: true, encoding: .utf8)
    } catch {
        fputs("could not write output: \(error)\n", stderr)
        exit(1)
    }
} else {
    print(output, terminator: "")
}
