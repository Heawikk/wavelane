import QtQuick
import QtQuick.Layouts
import Wavelane

/*!
    "Моя волна": a heading and one round button, over a backdrop that moves
    with the music.

    The backdrop and the bars under the buttons both read the player's audio
    analysis, so a beat is visible as it happens. With nothing playing they
    drift slowly instead of freezing, so the page is never a blank screen.
*/
Item {
    id: root

    readonly property bool waveActive: wave.started && player.hasTrack
                                       && player.context === "wave"
    readonly property bool audible: player.playing

    // The looks the listener chose in the settings.
    readonly property bool blobsOn: app.blobsEnabled
    readonly property string vizStyle: app.visualizerStyle

    //! Seconds of animation, running faster the louder the music is. It only
    //! advances while something on the page is actually moving, so with the blobs
    //! and the visualizer both off the page costs nothing to keep open.
    property real clock: 0
    readonly property var tap: player.spectrum

    // A colour set for each mood, so changing the dial visibly changes the page.
    readonly property var palettes: ({
        "any":       ["#2f63e6", "#8a5cff", "#27c9e8"],
        "energetic": ["#ff5a36", "#ff2e93", "#ffb020"],
        "party":     ["#ff2ea6", "#7a3cff", "#ffd23f"],
        "chill":     ["#2fd4a6", "#2f7fe6", "#7be0ff"],
        "calm":      ["#3f7fd6", "#6b6bd6", "#52c7c7"],
        "focus":     ["#3ddc97", "#1fa3a3", "#8bd450"],
        "sad":       ["#3b4fc9", "#6a3fa0", "#2b7aa8"]
    })
    readonly property var colors: palettes[wave.mood] || palettes["any"]

    // What drives the picture: the real analysis while music plays, and a slow
    // breathing of its own otherwise.
    readonly property real breath: 0.5 + 0.5 * Math.sin(root.clock * 0.9)

    // How much the music, rather than the breathing, is in charge. It glides
    // between the two, so starting or pausing swells or settles the blobs
    // instead of snapping them from one picture to the other.
    property real alive: audible ? 1 : 0
    Behavior on alive {
        NumberAnimation { duration: 1300; easing.type: Easing.InOutSine }
    }

    // The last analysis heard, held while nothing plays so the fade has
    // something to fade from.
    property real heldLevel: 0
    property real heldBass: 0
    property real heldMid: 0
    property real heldTreble: 0
    property var heldBands: []

    readonly property real idleLevel: 0.10 + 0.05 * breath
    readonly property real idleBass: 0.08 + 0.10 * breath
    readonly property real idleMid: 0.06 + 0.05 * breath
    readonly property real idleTreble: 0.03

    readonly property real level: idleLevel + (heldLevel - idleLevel) * alive
    readonly property real bass: idleBass + (heldBass - idleBass) * alive
    readonly property real mid: idleMid + (heldMid - idleMid) * alive
    readonly property real treble: idleTreble + (heldTreble - idleTreble) * alive

    // The bars, blended the same way.
    property var shownBands: idleBands

    FrameAnimation {
        running: root.visible && (root.blobsOn || root.vizStyle !== "off")
        onTriggered: {
            root.clock += frameTime * (0.55 + 1.1 * root.level)
            if (root.audible) {
                root.heldLevel = root.tap.level
                root.heldBass = root.tap.bass
                root.heldMid = root.tap.mid
                root.heldTreble = root.tap.treble
                root.heldBands = root.tap.bands
            }
            const idle = root.idleBands
            const held = root.heldBands
            const a = root.alive
            const out = []
            for (let i = 0; i < 32; ++i) {
                const h = held && held.length > i ? held[i] : 0
                out.push(idle[i] + (h - idle[i]) * a)
            }
            root.shownBands = out
        }
    }

    //! Wash the blobs with the colour of a reaction.
    function pulse(color, strength) {
        if (vibeLoader.item)
            vibeLoader.item.pulse(color, strength)
    }

    function toggle() {
        if (!root.waveActive)
            wave.start()
        else
            player.togglePlayPause()
    }

    // Not loaded at all when switched off, so the shader costs the GPU nothing.
    Loader {
        id: vibeLoader
        anchors.fill: parent
        active: root.blobsOn

        sourceComponent: VibeBackground {
            clock: root.clock
            level: root.level
            bass: root.bass
            mid: root.mid
            treble: root.treble
            colorA: root.colors[0]
            colorB: root.colors[1]
            colorC: root.colors[2]
        }
    }

    ColumnLayout {
        anchors.centerIn: parent
        // sit a little above the middle, where the eye lands
        anchors.verticalCenterOffset: -50
        spacing: 40

        Item {
            Layout.alignment: Qt.AlignHCenter
            implicitWidth: title.implicitWidth
            implicitHeight: title.implicitHeight
            // the heading breathes with the beat, very slightly
            scale: 1.0 + 0.018 * root.bass

            // a soft shadow keeps the white heading legible over bright colour
            Text {
                x: 0
                y: 3
                text: title.text
                color: Qt.rgba(0, 0, 0, 0.35)
                font: title.font
            }
            Text {
                id: title
                text: qsTr("Моя волна")
                color: Theme.text
                font.family: Theme.sans
                font.pixelSize: 88
                font.weight: Font.Black
                font.letterSpacing: -2
            }
        }

        // only ever says something when the wave could not start
        Mono {
            Layout.alignment: Qt.AlignHCenter
            Layout.maximumWidth: 460
            visible: wave.statusMessage !== ""
            text: wave.statusMessage
            color: Theme.warning
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideNone
            lineHeight: 1.4
        }

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            // room for the ring of rays around the play button
            spacing: root.vizStyle === "ring" ? 46 : 26

            // the wave has no "previous", but the row keeps its shape
            RoundButton {
                glyph: Theme.iPrev
                size: 46
                enabledWhen: false
            }

            Item {
                implicitWidth: 76
                implicitHeight: 76

                // Two rings that swell with the beat, around the play button.
                Rectangle {
                    anchors.centerIn: parent
                    width: 76 * (1.18 + 0.55 * root.bass)
                    height: width
                    radius: width / 2
                    color: "transparent"
                    border.color: Qt.rgba(1, 1, 1, 0.10 + 0.40 * root.level)
                    border.width: 1
                    opacity: root.alive
                    visible: root.alive > 0.01 && root.vizStyle !== "ring"
                }
                Rectangle {
                    anchors.centerIn: parent
                    width: 76 * (1.45 + 0.9 * root.bass)
                    height: width
                    radius: width / 2
                    color: "transparent"
                    border.color: Qt.rgba(1, 1, 1, 0.05 + 0.20 * root.level)
                    border.width: 1
                    opacity: root.alive
                    visible: root.alive > 0.01 && root.vizStyle !== "ring"
                }

                // the "ring" style: the spectrum as rays around the button
                Loader {
                    x: parent.width / 2
                    y: parent.height / 2
                    active: root.vizStyle === "ring"

                    sourceComponent: RingVisualizer {
                        bands: root.shownBands
                        tint: Qt.lighter(root.colors[2], 1.25)
                    }
                }

                RoundButton {
                    anchors.centerIn: parent
                    glyph: root.waveActive && player.playing ? Theme.iPause : Theme.iPlay
                    size: 76
                    filled: true
                    enabledWhen: !wave.loading
                    tooltip: root.waveActive ? (player.playing ? qsTr("Пауза") : qsTr("Продолжить"))
                                             : qsTr("Слушать волну")
                    onClicked: root.toggle()
                }
            }

            RoundButton {
                glyph: Theme.iNext
                size: 46
                enabledWhen: root.waveActive
                tooltip: qsTr("Следующий трек")
                onClicked: wave.playNext()
            }
        }

        Visualizer {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 18
            visible: root.vizStyle === "bars" || root.vizStyle === "wave" || root.vizStyle === "dots"
            style: root.vizStyle
            tint: Qt.lighter(root.colors[2], 1.25)
            bands: root.shownBands
        }
    }

    // A slow travelling ripple across the bars while nothing plays.
    readonly property var idleBands: {
        const out = []
        for (let i = 0; i < 32; ++i)
            out.push(0.03 + 0.05 * (0.5 + 0.5 * Math.sin(root.clock * 1.6 - i * 0.45)))
        return out
    }
}
