import QtQuick
import QtQuick.Layouts
import Wavelane

/*!
    "Моя волна": a heading and one round button.

    Everything else about the wave — the dials in the window bar, what is
    playing in the strip below — lives elsewhere, so this page stays empty
    on purpose.
*/
Item {
    id: root

    readonly property bool waveActive: wave.started && player.hasTrack
                                       && player.context === "wave"

    function toggle() {
        if (!root.waveActive)
            wave.start()
        else
            player.togglePlayPause()
    }

    ColumnLayout {
        anchors.centerIn: parent
        // sit a little above the middle, where the eye lands
        anchors.verticalCenterOffset: -30
        spacing: 40

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: qsTr("Моя волна")
            color: Theme.text
            font.family: Theme.sans
            font.pixelSize: 88
            font.weight: Font.Black
            font.letterSpacing: -2
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
            spacing: 26

            // the wave has no "previous", but the row keeps its shape
            RoundButton {
                glyph: Theme.iPrev
                size: 46
                enabledWhen: false
            }

            RoundButton {
                glyph: root.waveActive && player.playing ? Theme.iPause : Theme.iPlay
                size: 76
                filled: true
                enabledWhen: !wave.loading
                tooltip: root.waveActive ? (player.playing ? qsTr("Пауза") : qsTr("Продолжить"))
                                         : qsTr("Слушать волну")
                onClicked: root.toggle()
            }

            RoundButton {
                glyph: Theme.iNext
                size: 46
                enabledWhen: root.waveActive
                tooltip: qsTr("Следующий трек")
                onClicked: wave.playNext()
            }
        }
    }
}
