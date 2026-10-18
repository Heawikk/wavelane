import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    "Old file or new?" for every upload or import that turned out to be a track
    the library already has.

    Each row shows the two files side by side so the choice is informed rather
    than a guess; the server's recommendation (a clearly better copy) is
    pre-selected, and three buttons settle everything at once for the common
    case of hundreds of conflicts after a big import.
*/
Popup {
    id: root

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    dim: true
    focus: true
    padding: 0
    width: Math.min(parent ? parent.width - 80 : 900, 940)
    height: Math.min(parent ? parent.height - 80 : 640, 640)
    closePolicy: Popup.CloseOnEscape

    //! conflict id -> "keep_old" | "replace"
    property var choices: ({})

    readonly property var items: library.conflicts
    readonly property int replaceCount: countOf("replace")

    Overlay.modal: Rectangle { color: Theme.alpha("#000000", 0.6) }

    background: Rectangle {
        color: Theme.bar
        border.color: Theme.borderStrong
        border.width: 1
    }

    function countOf(action) {
        let n = 0
        for (let i = 0; i < items.length; ++i) {
            if ((choices[items[i].id] || items[i].recommended) === action)
                ++n
        }
        return n
    }

    function choiceFor(conflict) {
        return choices[conflict.id] || conflict.recommended
    }

    function setChoice(id, action) {
        const next = Object.assign({}, choices)
        next[id] = action
        choices = next
    }

    function setAll(mode) {
        const next = {}
        for (let i = 0; i < items.length; ++i)
            next[items[i].id] = mode === "recommended" ? items[i].recommended : mode
        choices = next
    }

    function apply() {
        const resolutions = []
        for (let i = 0; i < items.length; ++i)
            resolutions.push({ id: items[i].id, action: choiceFor(items[i]) })
        library.resolveConflicts(resolutions)
    }

    function formatSize(bytes) {
        if (!bytes)
            return "—"
        return bytes >= 1048576 ? (bytes / 1048576).toFixed(1) + " МБ"
                                : Math.max(1, Math.round(bytes / 1024)) + " КБ"
    }

    function formatTime(ms) {
        if (!ms)
            return "—"
        const total = Math.round(ms / 1000)
        const s = total % 60
        return Math.floor(total / 60) + ":" + (s < 10 ? "0" : "") + s
    }

    function describe(info) {
        return [info.quality || "—", formatTime(info.duration_ms), formatSize(info.file_size)]
            .join("   ·   ")
    }

    // nothing left to ask about: close by itself
    onItemsChanged: if (opened && items.length === 0) close()
    onAboutToShow: choices = ({})

    contentItem: ColumnLayout {
        spacing: 0

        SectionHeader {
            Layout.fillWidth: true
            title: qsTr("Конфликты · %1").arg(root.items.length)

            IconButton {
                glyph: Theme.iClose
                tooltip: qsTr("Решить позже")
                onClicked: root.close()
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.margins: 16
            Layout.bottomMargin: 10
            text: qsTr("Эти треки уже есть в библиотеке, но файл другой. Оставить прежний или заменить новым? "
                       + "Лайки, плейлисты и история сохранятся при любом выборе.")
            color: Theme.muted
            font.family: Theme.sans
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
            lineHeight: 1.2
        }

        // column captions
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            spacing: 14

            Mono { Layout.fillWidth: true; text: qsTr("Трек"); color: Theme.faint; font.pixelSize: 10 }
            Mono { Layout.preferredWidth: 220; text: qsTr("Сейчас в библиотеке"); color: Theme.faint; font.pixelSize: 10 }
            Mono { Layout.preferredWidth: 220; text: qsTr("Новый файл"); color: Theme.faint; font.pixelSize: 10 }
            Item { Layout.preferredWidth: 188 }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            Layout.topMargin: 6
            color: Theme.border
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: root.items
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: FlatScrollBar {}

            delegate: Rectangle {
                id: row

                required property var modelData
                readonly property string choice: root.choiceFor(modelData)

                width: ListView.view.width
                height: 62
                color: hover.hovered ? Theme.rowHover : "transparent"

                HoverHandler { id: hover }

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: Theme.border
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    spacing: 14

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Text {
                            Layout.fillWidth: true
                            text: row.modelData.title
                            color: Theme.text
                            font.family: Theme.sans
                            font.pixelSize: Theme.fontBody
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: row.modelData.artist_name
                            color: Theme.muted
                            font.family: Theme.sans
                            font.pixelSize: Theme.fontSmall
                            elide: Text.ElideRight
                        }
                    }

                    Mono {
                        Layout.preferredWidth: 220
                        text: root.describe(row.modelData.existing)
                        color: row.choice === "keep_old" ? Theme.text : Theme.faint
                        font.letterSpacing: 0.2
                    }

                    ColumnLayout {
                        Layout.preferredWidth: 220
                        // A nested layout fills the leftover width by default, which
                        // would share it with the title column and shove every
                        // column out from under its caption.
                        Layout.fillWidth: false
                        spacing: 2

                        Mono {
                            Layout.fillWidth: true
                            text: root.describe(row.modelData.incoming)
                            color: row.choice === "replace" ? Theme.text : Theme.faint
                            font.letterSpacing: 0.2
                        }
                        Mono {
                            Layout.fillWidth: true
                            visible: row.modelData.recommended === "replace"
                            text: qsTr("новый лучше")
                            color: Theme.positive
                            font.pixelSize: 10
                        }
                    }

                    Segmented {
                        Layout.preferredWidth: 188
                        stretch: true
                        options: [
                            { value: "keep_old", label: qsTr("Старый") },
                            { value: "replace",  label: qsTr("Новый") }
                        ]
                        current: row.choice
                        onPicked: function(value) { root.setChoice(row.modelData.id, value) }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.border
        }

        // --- settle the lot at once ---
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 14
            spacing: 8

            FlatButton {
                text: qsTr("Все старые")
                onClicked: root.setAll("keep_old")
            }
            FlatButton {
                text: qsTr("Все новые")
                onClicked: root.setAll("replace")
            }
            FlatButton {
                text: qsTr("Как советует сервер")
                onClicked: root.setAll("recommended")
            }

            Item { Layout.fillWidth: true }

            Mono {
                text: qsTr("заменить: %1  ·  оставить: %2")
                          .arg(root.replaceCount).arg(root.items.length - root.replaceCount)
                color: Theme.faint
            }

            FlatButton {
                text: qsTr("Позже")
                onClicked: root.close()
            }
            FlatButton {
                primary: true
                text: qsTr("Применить")
                enabledWhen: root.items.length > 0
                onClicked: root.apply()
            }
        }
    }
}
