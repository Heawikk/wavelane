import QtQuick
import Wavelane

/*!
    The flowing, glowing backdrop of the wave page.

    A fragment shader draws a handful of drifting metaballs. The animation
    clock runs faster the louder the music is, and the beat, mids and treble
    each drive a different part of the picture, so it follows what is playing
    rather than looping on its own. The three colours are properties so the
    palette can change with the mood.
*/
Item {
    id: root

    property real level: 0
    property real bass: 0
    property real mid: 0
    property real treble: 0

    property color colorA: Theme.accent
    property color colorB: "#8a5cff"
    property color colorC: "#27c9e8"

    //! Seconds of animation; sped up by loudness. Read by the rest of the page.
    property real clock: 0

    Behavior on colorA { ColorAnimation { duration: 1100 } }
    Behavior on colorB { ColorAnimation { duration: 1100 } }
    Behavior on colorC { ColorAnimation { duration: 1100 } }

    // Paused with the page, so nothing is drawn while it is hidden.
    FrameAnimation {
        running: root.visible
        onTriggered: root.clock += frameTime * (0.55 + 1.1 * root.level)
    }

    ShaderEffect {
        id: effect
        anchors.fill: parent

        property real time: root.clock
        property real level: root.level
        property real bass: root.bass
        property real mid: root.mid
        property real treble: root.treble
        property real aspect: width / Math.max(1, height)
        property color colorA: root.colorA
        property color colorB: root.colorB
        property color colorC: root.colorC
        property color background: Theme.bg

        fragmentShader: "qrc:/shaders/vibe.frag.qsb"
    }

    // If the GPU backend cannot run the shader, a quiet glow is better than a black page.
    Rectangle {
        anchors.fill: parent
        visible: effect.status === ShaderEffect.Error
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.bg }
            GradientStop { position: 0.5; color: Qt.rgba(root.colorA.r, root.colorA.g, root.colorA.b, 0.25) }
            GradientStop { position: 1.0; color: Theme.bg }
        }
    }
}
