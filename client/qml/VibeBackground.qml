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

    //! Seconds of animation, advanced by the page that owns this (faster when it is
    //! loud), so the page can stop the clock altogether when nothing moves.
    property real clock: 0

    //! A coloured wave that passes through the blobs, used to answer a like or a dislike.
    property real flash: 0
    property color flashColor: "#ff3b5c"

    //! Wash the blobs with `color` and let it fade; `strength` is 0..1.
    function pulse(color, strength) {
        flashColor = color
        flashAnimation.stop()
        flashAnimation.peak = strength
        flashAnimation.start()
    }

    SequentialAnimation {
        id: flashAnimation
        property real peak: 1
        NumberAnimation { target: root; property: "flash"; to: flashAnimation.peak; duration: 260; easing.type: Easing.OutCubic }
        NumberAnimation { target: root; property: "flash"; to: 0; duration: 1400; easing.type: Easing.InOutQuad }
    }

    Behavior on colorA { ColorAnimation { duration: 1100 } }
    Behavior on colorB { ColorAnimation { duration: 1100 } }
    Behavior on colorC { ColorAnimation { duration: 1100 } }

    ShaderEffect {
        id: effect
        anchors.fill: parent

        property real time: root.clock
        property real level: root.level
        property real bass: root.bass
        property real mid: root.mid
        property real treble: root.treble
        property real aspect: width / Math.max(1, height)
        property real flash: root.flash
        property color colorA: root.colorA
        property color colorB: root.colorB
        property color colorC: root.colorC
        property color background: Theme.bg
        property color flashColor: root.flashColor

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
