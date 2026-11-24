import AppKit
import CoreGraphics
import CoreImage
import Foundation

struct IconSpec {
    let inputPath: String
    let outputMasterPath: String
    let sourceCenterX: Double
    let sourceCenterY: Double // Top-down pixel coordinate
    let sourceTickRadius: Double
    let safeSourceBgRadius: Double
    let rimAlpha: CGFloat
}

let targetCanvas = 1024
let squircleSize = 824.0
let squircleHalf = squircleSize / 2.0 // 412
let superellipseExponent = 4.6
let targetTickRadius = 252.0

func loadRGBA(_ path: String) -> ([UInt8], Int, Int) {
    guard let image = NSImage(contentsOfFile: path),
          let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil)
    else {
        fputs("Failed to load image: \(path)\n", stderr)
        exit(1)
    }
    let width = cgImage.width
    let height = cgImage.height
    var bytes = [UInt8](repeating: 0, count: width * height * 4)
    let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!
    guard let ctx = CGContext(
        data: &bytes,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: width * 4,
        space: colorSpace,
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else {
        exit(1)
    }
    ctx.draw(cgImage, in: CGRect(x: 0, y: 0, width: width, height: height))
    // Unpremultiply so bilinear interpolation in radial extension is exact
    for i in stride(from: 0, to: bytes.count, by: 4) {
        let a = Double(bytes[i + 3]) / 255.0
        if a > 0.001 && a < 0.999 {
            bytes[i] = UInt8(min(255.0, Double(bytes[i]) / a))
            bytes[i + 1] = UInt8(min(255.0, Double(bytes[i + 1]) / a))
            bytes[i + 2] = UInt8(min(255.0, Double(bytes[i + 2]) / a))
        }
    }
    return (bytes, width, height)
}

@inline(__always)
func sampleBilinear(_ buf: [UInt8], _ w: Int, _ h: Int, _ x: Double, _ y: Double) -> (Double, Double, Double, Double) {
    let cx = max(0.0, min(Double(w - 1), x))
    let cy = max(0.0, min(Double(h - 1), y))
    let x0 = Int(floor(cx))
    let y0 = Int(floor(cy))
    let x1 = min(w - 1, x0 + 1)
    let y1 = min(h - 1, y0 + 1)
    let fx = cx - Double(x0)
    let fy = cy - Double(y0)

    func px(_ ix: Int, _ iy: Int) -> (Double, Double, Double, Double) {
        let idx = (iy * w + ix) * 4
        return (
            Double(buf[idx]) / 255.0,
            Double(buf[idx + 1]) / 255.0,
            Double(buf[idx + 2]) / 255.0,
            Double(buf[idx + 3]) / 255.0
        )
    }
    let p00 = px(x0, y0), p10 = px(x1, y0), p01 = px(x0, y1), p11 = px(x1, y1)
    let w00 = (1 - fx) * (1 - fy)
    let w10 = fx * (1 - fy)
    let w01 = (1 - fx) * fy
    let w11 = fx * fy
    return (
        p00.0 * w00 + p10.0 * w10 + p01.0 * w01 + p11.0 * w11,
        p00.1 * w00 + p10.1 * w10 + p01.1 * w01 + p11.1 * w11,
        p00.2 * w00 + p10.2 * w10 + p01.2 * w01 + p11.2 * w11,
        p00.3 * w00 + p10.3 * w10 + p01.3 * w01 + p11.3 * w11
    )
}

func superellipsePath(center: CGPoint, halfSize: CGFloat, exponent: Double) -> CGPath {
    let path = CGMutablePath()
    let steps = 720
    for step in 0...steps {
        let theta = (Double(step) / Double(steps)) * 2.0 * Double.pi
        let cosT = cos(theta)
        let sinT = sin(theta)
        let x = Double(center.x) + copysign(pow(abs(cosT), 2.0 / exponent), cosT) * Double(halfSize)
        let y = Double(center.y) + copysign(pow(abs(sinT), 2.0 / exponent), sinT) * Double(halfSize)
        if step == 0 {
            path.move(to: CGPoint(x: x, y: y))
        } else {
            path.addLine(to: CGPoint(x: x, y: y))
        }
    }
    path.closeSubpath()
    return path
}

func renderNormalizedMaster(_ spec: IconSpec) -> CGImage {
    let (src, sw, sh) = loadRGBA(spec.inputPath)
    let scale = targetTickRadius / spec.sourceTickRadius

    // Build seamless full-bleed 1024x1024 color field aligned to (512, 512)
    var field = [UInt8](repeating: 255, count: targetCanvas * targetCanvas * 4)
    let dialOuterTargetRadius = 338.0
    for ty in 0..<targetCanvas {
        for tx in 0..<targetCanvas {
            let dx = Double(tx) + 0.5 - 512.0
            let dy = Double(ty) + 0.5 - 512.0
            let targetR = hypot(dx, dy)
            let srcR = targetR / scale
            let sx = spec.sourceCenterX + dx / scale
            let sy = spec.sourceCenterY + dy / scale
            let direct = sampleBilinear(src, sw, sh, sx, sy)

            var r = direct.0, g = direct.1, b = direct.2
            if targetR > dialOuterTargetRadius {
                // Sample a 9-point angular+radial neighborhood inside safeSourceBgRadius to eliminate radial streak artifacts on textured surfaces
                let clampedSrcR = min(srcR, spec.safeSourceBgRadius)
                let ux = targetR > 0 ? dx / targetR : 0
                let uy = targetR > 0 ? dy / targetR : 0
                let txPerp = -uy
                let tyPerp = ux
                var sr = 0.0, sg = 0.0, sb = 0.0
                let offsets: [(Double, Double)] = [
                    (0, 0), (-6, -8), (-6, 8), (-14, -16), (-14, 16),
                    (-22, -24), (-22, 24), (-10, 0), (-20, 0),
                ]
                for (dr, dt) in offsets {
                    let s = sampleBilinear(
                        src, sw, sh,
                        spec.sourceCenterX + ux * (clampedSrcR + dr) + txPerp * dt,
                        spec.sourceCenterY + uy * (clampedSrcR + dr) + tyPerp * dt
                    )
                    sr += s.0; sg += s.1; sb += s.2
                }
                sr /= Double(offsets.count)
                sg /= Double(offsets.count)
                sb /= Double(offsets.count)
                // Add ultra-subtle deterministic micro-grain matching the dark anodized finish
                let hash = sin(Double(tx) * 12.9898 + Double(ty) * 78.233) * 43758.5453
                let grain = ((hash - floor(hash)) - 0.5) * 0.014
                let radialShade = max(0.93, 1.0 - max(0.0, (srcR - spec.safeSourceBgRadius) / 260.0) * 0.07)
                let blendStart = spec.safeSourceBgRadius * scale - 14.0
                let t = max(0.0, min(1.0, (targetR - blendStart) / 20.0))
                let effectiveT = max(t, 1.0 - direct.3)
                let extR = max(0.0, min(1.0, sr * radialShade + grain))
                let extG = max(0.0, min(1.0, sg * radialShade + grain))
                let extB = max(0.0, min(1.0, sb * radialShade + grain))
                r = direct.0 * (1.0 - effectiveT) + extR * effectiveT
                g = direct.1 * (1.0 - effectiveT) + extG * effectiveT
                b = direct.2 * (1.0 - effectiveT) + extB * effectiveT
            }
            let idx = (ty * targetCanvas + tx) * 4
            field[idx] = UInt8(max(0.0, min(255.0, round(r * 255.0))))
            field[idx + 1] = UInt8(max(0.0, min(255.0, round(g * 255.0))))
            field[idx + 2] = UInt8(max(0.0, min(255.0, round(b * 255.0))))
            field[idx + 3] = 255
        }
    }

    let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!
    let fieldCtx = CGContext(
        data: &field,
        width: targetCanvas,
        height: targetCanvas,
        bitsPerComponent: 8,
        bytesPerRow: targetCanvas * 4,
        space: colorSpace,
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    )!
    let fieldImage = fieldCtx.makeImage()!

    // Final 1024x1024 canvas with Apple HIG shadow + continuous squircle clip + subtle specular rim
    let outCtx = CGContext(
        data: nil,
        width: targetCanvas,
        height: targetCanvas,
        bitsPerComponent: 8,
        bytesPerRow: targetCanvas * 4,
        space: colorSpace,
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    )!
    outCtx.interpolationQuality = .high
    outCtx.setAllowsAntialiasing(true)
    outCtx.setShouldAntialias(true)

    let squircle = superellipsePath(
        center: CGPoint(x: 512, y: 512),
        halfSize: CGFloat(squircleHalf),
        exponent: superellipseExponent
    )

    // 1. Apple HIG ambient drop shadow
    outCtx.saveGState()
    outCtx.setShadow(
        offset: CGSize(width: 0, height: -10),
        blur: 24,
        color: CGColor(srgbRed: 0, green: 0, blue: 0, alpha: 0.28)
    )
    outCtx.addPath(squircle)
    outCtx.setFillColor(CGColor(srgbRed: 0, green: 0, blue: 0, alpha: 1.0))
    outCtx.fillPath()
    outCtx.restoreGState()

    // 2. Clipped icon body (note: CGImage draw flips vertically unless matched; field row 0 is top)
    outCtx.saveGState()
    outCtx.addPath(squircle)
    outCtx.clip()
    outCtx.draw(fieldImage, in: CGRect(x: 0, y: 0, width: targetCanvas, height: targetCanvas))

    // 3. Subtle 1.5px inner rim highlight for native macOS glass edge definition
    outCtx.addPath(squircle)
    outCtx.setLineWidth(3.0)
    outCtx.setStrokeColor(CGColor(srgbRed: 1, green: 1, blue: 1, alpha: spec.rimAlpha))
    outCtx.strokePath()
    outCtx.restoreGState()

    return outCtx.makeImage()!
}

let ciContext = CIContext(options: [.useSoftwareRenderer: false])

func resizeIcon(_ master: CGImage, pixelSize: Int) -> CGImage {
    if pixelSize == targetCanvas { return master }
    let scale = Double(pixelSize) / Double(targetCanvas)
    var image = CIImage(cgImage: master)
    let lanczos = CIFilter(name: "CILanczosScaleTransform")!
    lanczos.setValue(image, forKey: kCIInputImageKey)
    lanczos.setValue(scale, forKey: kCIInputScaleKey)
    lanczos.setValue(1.0, forKey: kCIInputAspectRatioKey)
    image = lanczos.outputImage!

    if pixelSize <= 128 {
        let sharpen = CIFilter(name: "CIUnsharpMask")!
        sharpen.setValue(image, forKey: kCIInputImageKey)
        sharpen.setValue(pixelSize <= 32 ? 0.9 : 1.1, forKey: kCIInputRadiusKey)
        sharpen.setValue(pixelSize <= 32 ? 0.42 : 0.28, forKey: kCIInputIntensityKey)
        if let sharpened = sharpen.outputImage {
            image = sharpened
        }
    }
    let rect = CGRect(x: 0, y: 0, width: pixelSize, height: pixelSize)
    return ciContext.createCGImage(image, from: rect)!
}

func writePNG(_ image: CGImage, to path: String) {
    let rep = NSBitmapImageRep(cgImage: image)
    guard let data = rep.representation(using: .png, properties: [:]) else {
        fputs("Failed to encode PNG: \(path)\n", stderr)
        exit(1)
    }
    try! data.write(to: URL(fileURLWithPath: path), options: .atomic)
}

let args = CommandLine.arguments
guard args.count == 5 else {
    fputs("Usage: swift generate_macos_icons.swift <light_src> <dark_src> <icons_dir> <public_dir>\n", stderr)
    exit(64)
}

let lightSrc = args[1]
let darkSrc = args[2]
let iconsDir = args[3]
let publicDir = args[4]

let fm = FileManager.default
let appiconsetDir = "\(iconsDir)/Assets.xcassets/AppIcon.appiconset"
let iconsetTmpDir = "\(NSTemporaryDirectory())aq-iconset-\(UUID().uuidString).iconset"
try! fm.createDirectory(atPath: appiconsetDir, withIntermediateDirectories: true)
try! fm.createDirectory(atPath: iconsetTmpDir, withIntermediateDirectories: true)
defer { try? fm.removeItem(atPath: iconsetTmpDir) }

let lightMaster = renderNormalizedMaster(IconSpec(
    inputPath: lightSrc,
    outputMasterPath: "\(iconsDir)/icon.png",
    sourceCenterX: 512.0,
    sourceCenterY: 511.5,
    sourceTickRadius: 241.5,
    safeSourceBgRadius: 348.0,
    rimAlpha: 0.22
))

let darkMaster = renderNormalizedMaster(IconSpec(
    inputPath: darkSrc,
    outputMasterPath: "\(iconsDir)/icon-dark.png",
    sourceCenterX: 511.5,
    sourceCenterY: 511.5,
    sourceTickRadius: 289.5,
    safeSourceBgRadius: 456.0,
    rimAlpha: 0.14
))

// Standard Tauri icons
writePNG(lightMaster, to: "\(iconsDir)/icon.png")
writePNG(darkMaster, to: "\(iconsDir)/icon-dark.png")
writePNG(resizeIcon(lightMaster, pixelSize: 32), to: "\(iconsDir)/32x32.png")
writePNG(resizeIcon(lightMaster, pixelSize: 128), to: "\(iconsDir)/128x128.png")
writePNG(resizeIcon(lightMaster, pixelSize: 256), to: "\(iconsDir)/128x128@2x.png")

// Crisp 64px badges for in-app sidebar header (Light + Dark)
writePNG(resizeIcon(lightMaster, pixelSize: 64), to: "\(publicDir)/icon-light-64.png")
writePNG(resizeIcon(darkMaster, pixelSize: 64), to: "\(publicDir)/icon-dark-64.png")

// Full macOS mipmap ladder (16..1024) for both iconutil (.icns) and actool (Assets.car Light + Dark)
let ladder: [(point: Int, scale: Int, pixels: Int)] = [
    (16, 1, 16), (16, 2, 32),
    (32, 1, 32), (32, 2, 64),
    (128, 1, 128), (128, 2, 256),
    (256, 1, 256), (256, 2, 512),
    (512, 1, 512), (512, 2, 1024),
]

var xcImages: [[String: Any]] = []
for slot in ladder {
    let suffix = slot.scale == 2 ? "@2x" : ""
    let baseName = "icon_\(slot.point)x\(slot.point)\(suffix)"
    let lightImg = resizeIcon(lightMaster, pixelSize: slot.pixels)
    let darkImg = resizeIcon(darkMaster, pixelSize: slot.pixels)

    writePNG(lightImg, to: "\(iconsetTmpDir)/\(baseName).png")
    let lightFile = "light_\(slot.point)x\(slot.point)\(suffix).png"
    let darkFile = "dark_\(slot.point)x\(slot.point)\(suffix).png"
    writePNG(lightImg, to: "\(appiconsetDir)/\(lightFile)")
    writePNG(darkImg, to: "\(appiconsetDir)/\(darkFile)")

    xcImages.append([
        "filename": lightFile,
        "idiom": "mac",
        "scale": "\(slot.scale)x",
        "size": "\(slot.point)x\(slot.point)",
    ])
    xcImages.append([
        "appearances": [["appearance": "luminosity", "value": "dark"]],
        "filename": darkFile,
        "idiom": "mac",
        "scale": "\(slot.scale)x",
        "size": "\(slot.point)x\(slot.point)",
    ])
}

let contentsJSON: [String: Any] = [
    "images": xcImages,
    "info": ["author": "xcode", "version": 1],
]
let jsonData = try! JSONSerialization.data(withJSONObject: contentsJSON, options: [.prettyPrinted, .sortedKeys])
try! (String(data: jsonData, encoding: .utf8)! + "\n").write(
    toFile: "\(appiconsetDir)/Contents.json",
    atomically: true,
    encoding: .utf8
)

let iconutil = Process()
iconutil.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
iconutil.arguments = ["-c", "icns", iconsetTmpDir, "-o", "\(iconsDir)/icon.icns"]
try! iconutil.run()
iconutil.waitUntilExit()
guard iconutil.terminationStatus == 0 else {
    fputs("iconutil failed\n", stderr)
    exit(1)
}
print("Generated normalized Light + Dark macOS icon set successfully.")
