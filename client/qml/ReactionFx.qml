import QtQuick
import Wavelane

/*!
    The answer to a like or a dislike: a stream of small glowing sparks leaves the
    button and flies to the glowing blobs of the wave page, which light up in the
    colour of the reaction when it arrives. Red for a like, grey for a dislike.

    Where the blobs are not on screen the sparks drift up from the button and fade.

    This item only draws; it never takes the mouse.
*/
Item {
    id: root

    enabled: false

    //! The first spark has reached its target.
    signal arrived(string kind)

    readonly property var looks: ({
        "like":    { core: "#ff6b86", glow: "#ff2e55", ring: "#ff5a78" },
        "dislike": { core: "#c4c9d4", glow: "#8b909c", ring: "#a4a9b6" }
    })

    /*!
        Send sparks from the centre of `source`. With a `target` they fly to its
        centre; without one they rise and fade.
    */
    function play(kind, source, target) {
        if (!source)
            return
        const look = looks[kind] || looks["like"]
        const from = source.mapToItem(root, source.width / 2, source.height / 2)
        const count = 10

        for (let i = 0; i < count; ++i) {
            let end, control
            if (target) {
                const to = target.mapToItem(root, target.width / 2, target.height / 2)
                end = Qt.point(to.x + (Math.random() - 0.5) * 70, to.y + (Math.random() - 0.5) * 50)
                // The path bows upward and sideways, a different amount for each spark.
                const bow = 70 + Math.random() * 130
                control = Qt.point((from.x + end.x) / 2 + (Math.random() - 0.5) * 220,
                                   Math.min(from.y, end.y) - bow)
            } else {
                end = Qt.point(from.x + (Math.random() - 0.5) * 160, from.y - 110 - Math.random() * 90)
                control = Qt.point(from.x + (Math.random() - 0.5) * 100, from.y - 50 - Math.random() * 40)
            }

            orb.createObject(root, {
                x0: from.x, y0: from.y, x1: end.x, y1: end.y,
                cx: control.x, cy: control.y,
                size: 6 + Math.random() * 7,
                core: look.core, glow: look.glow,
                delay: i * 45,
                // the first spark always takes the same time, so the ring can meet it
                travel: i === 0 ? 850 : (target ? 800 : 700) + Math.random() * 260,
                fadeOnly: !target,
                lead: target !== null && target !== undefined && i === 0,
                kind: kind
            })
        }

        if (target) {
            const to2 = target.mapToItem(root, target.width / 2, target.height / 2)
            // A ring opens where the sparks land, as the first one gets there.
            ring.createObject(root, { cx: to2.x, cy: to2.y, tone: look.ring, delay: 850 })
        }
    }

    Component {
        id: orb

        Item {
            id: spark

            property real x0: 0
            property real y0: 0
            property real x1: 0
            property real y1: 0
            property real cx: 0
            property real cy: 0
            property real size: 8
            property color core: "white"
            property color glow: "white"
            property int delay: 0
            property int travel: 800
            property bool fadeOnly: false
            property bool lead: false
            property string kind: "like"

            // 0 at the button, 1 at the target
            property real t: 0
            readonly property real u: 1 - t

            // a quadratic curve from the button through the control point to the target
            x: u * u * x0 + 2 * u * t * cx + t * t * x1
            y: u * u * y0 + 2 * u * t * cy + t * t * y1
            width: 0
            height: 0
            opacity: Math.min(1, t * 10) * (t > 0.8 ? (1 - t) / 0.2 : 1)
            scale: fadeOnly ? 1 - 0.4 * t : 1 + 0.5 * Math.sin(t * Math.PI) - 0.45 * t

            Rectangle {
                width: spark.size * 3.4
                height: width
                radius: width / 2
                x: -width / 2
                y: -height / 2
                color: Qt.rgba(spark.glow.r, spark.glow.g, spark.glow.b, 0.16)
            }
            Rectangle {
                width: spark.size * 2
                height: width
                radius: width / 2
                x: -width / 2
                y: -height / 2
                color: Qt.rgba(spark.glow.r, spark.glow.g, spark.glow.b, 0.34)
            }
            Rectangle {
                width: spark.size
                height: width
                radius: width / 2
                x: -width / 2
                y: -height / 2
                color: spark.core
            }

            SequentialAnimation on t {
                PauseAnimation { duration: spark.delay }
                NumberAnimation {
                    from: 0
                    to: 1
                    duration: spark.travel
                    easing.type: spark.fadeOnly ? Easing.OutCubic : Easing.InOutSine
                }
                ScriptAction {
                    script: {
                        if (spark.lead)
                            root.arrived(spark.kind)
                        spark.destroy()
                    }
                }
            }
        }
    }

    Component {
        id: ring

        Rectangle {
            id: wave

            property real cx: 0
            property real cy: 0
            property color tone: "white"
            property int delay: 0

            property real p: 0

            width: 40 + 220 * p
            height: width
            radius: width / 2
            x: cx - width / 2
            y: cy - height / 2
            color: "transparent"
            border.width: 2
            border.color: Qt.rgba(tone.r, tone.g, tone.b, 0.7)
            opacity: p <= 0 ? 0 : 1 - p

            SequentialAnimation on p {
                PauseAnimation { duration: wave.delay }
                NumberAnimation { from: 0.001; to: 1; duration: 800; easing.type: Easing.OutCubic }
                ScriptAction { script: wave.destroy() }
            }
        }
    }
}
