import QtQuick
import Wavelane

/*!
    The Wavelane mark: three wavy lines, on no background.

    The geometry and colours are the same as client/resources/make_icons.py
    uses for the application icon, so the logo in the app and the icon in the
    taskbar are one drawing.
*/
Canvas {
    id: root

    property real size: 28

    width: size
    height: size
    antialiasing: true

    readonly property var colours: ["#27c9e8", "#8a5cff", "#2f63e6"]
    readonly property var rows: [0.32, 0.50, 0.68]

    onSizeChanged: requestPaint()

    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        const w = root.size
        ctx.lineWidth = w * (w <= 24 ? 0.12 : 0.09)
        ctx.lineCap = "round"

        for (let i = 0; i < rows.length; ++i) {
            const y = rows[i] * w
            ctx.strokeStyle = colours[i]
            ctx.beginPath()
            ctx.moveTo(0.08 * w, y)
            ctx.bezierCurveTo(0.30 * w, y - 0.17 * w, 0.62 * w, y + 0.17 * w, 0.92 * w, y)
            ctx.stroke()
        }
    }
}
