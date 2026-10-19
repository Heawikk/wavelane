import QtQuick
import QtQuick.Controls
import Wavelane

/*!
    The small mark after a track's title that says it has words.

    Three short lines, like text on a page. When the words also follow the music,
    the middle line is lit and the mark takes the accent colour, the way the
    current line is lit in the lyrics view.
*/
Item {
    id: root

    //! "plain" or "synced"; anything else draws nothing.
    property string kind: "none"

    readonly property bool synced: kind === "synced"

    visible: kind === "plain" || kind === "synced"
    implicitWidth: 16
    implicitHeight: 14

    Column {
        anchors.centerIn: parent
        spacing: 2

        Repeater {
            model: [9, 12, 7]

            Rectangle {
                required property int index
                required property int modelData

                width: modelData
                height: 2
                radius: 1
                color: root.synced ? (index === 1 ? Theme.accentText : Theme.accent)
                                   : Theme.faint
                opacity: root.synced && index !== 1 ? 0.55 : 1.0
            }
        }
    }

    HoverHandler { id: hover }
    ToolTip.visible: hover.hovered && root.visible
    ToolTip.delay: 500
    ToolTip.text: root.synced ? qsTr("Есть текст, синхронизированный с музыкой")
                              : qsTr("Есть текст песни")
}
