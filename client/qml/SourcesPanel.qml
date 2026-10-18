import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import Wavelane

/*! "01 ИСТОЧНИКИ": what to browse, plus the account and the upload button. */
Rectangle {
    id: root

    property string source: "wave"

    signal selected(string source)

    color: Theme.panel

    readonly property var sources: [
        { id: "wave",      label: qsTr("Моя волна"),    glyph: Theme.iWave,      count: wave.queue.count },
        { id: "liked",     label: qsTr("Избранное"),    glyph: Theme.iHeart,     count: library.likedCount },
        { id: "catalogue", label: qsTr("Весь каталог"), glyph: Theme.iCatalogue, count: library.trackCount }
    ]

    function openUpload() { fileDialog.open() }

    FileDialog {
        id: fileDialog
        title: qsTr("Выберите аудиофайлы")
        fileMode: FileDialog.OpenFiles
        nameFilters: [
            qsTr("Аудио (*.mp3 *.flac *.m4a *.ogg *.opus *.wav *.aac *.wma *.aiff)"),
            qsTr("Все файлы (*)")
        ]
        onAccepted: library.uploadFiles(selectedFiles)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        SectionHeader {
            Layout.fillWidth: true
            number: "01"
            title: qsTr("Источники")

            IconButton {
                glyph: Theme.iRefresh
                tooltip: qsTr("Обновить")
                onClicked: {
                    library.loadStats()
                    library.loadLiked()
                    library.loadCatalogue()
                }
            }
        }

        Repeater {
            model: root.sources

            delegate: Rectangle {
                id: item

                required property var modelData
                readonly property bool on: root.source === modelData.id

                Layout.fillWidth: true
                Layout.preferredHeight: 40
                color: on ? Theme.rowSelected : (hover.containsMouse ? Theme.rowHover : "transparent")

                Rectangle {
                    width: 2
                    height: parent.height
                    color: Theme.accent
                    visible: item.on
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 12
                    spacing: 10

                    Icon {
                        glyph: item.modelData.glyph
                        font.pixelSize: 14
                        color: item.on ? Theme.accentText : Theme.faint
                    }
                    Text {
                        Layout.fillWidth: true
                        text: item.modelData.label
                        color: item.on ? Theme.text : Theme.muted
                        font.family: Theme.sans
                        font.pixelSize: Theme.fontBody
                        font.weight: item.on ? Font.DemiBold : Font.Normal
                        elide: Text.ElideRight
                    }
                    Mono {
                        text: item.modelData.count
                        color: Theme.faint
                    }
                }

                MouseArea {
                    id: hover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.selected(item.modelData.id)
                }
            }
        }

        Item { Layout.fillHeight: true }

        // --- how adventurous the wave is allowed to be ---
        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            Layout.bottomMargin: 12
            spacing: 4

            RowLayout {
                Layout.fillWidth: true
                Mono { text: qsTr("Разнообразие"); Layout.fillWidth: true }
                Mono {
                    text: Math.round(wave.diversity * 100) + "%"
                    color: Theme.text
                }
            }

            Slider {
                id: slider
                Layout.fillWidth: true
                implicitHeight: 18
                from: 0
                to: 1
                value: wave.diversity
                // One gesture, one request.
                onPressedChanged: if (!pressed) wave.setDiversity(value)

                background: Rectangle {
                    x: slider.leftPadding
                    y: slider.topPadding + slider.availableHeight / 2 - 1
                    width: slider.availableWidth
                    height: 2
                    color: Theme.borderStrong

                    Rectangle {
                        width: slider.visualPosition * parent.width
                        height: parent.height
                        color: Theme.accent
                    }
                }
                handle: Rectangle {
                    x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
                    y: slider.topPadding + slider.availableHeight / 2 - height / 2
                    width: 8
                    height: 12
                    color: Theme.light
                }
            }

            Mono {
                Layout.fillWidth: true
                text: qsTr("привычное  ←  →  неожиданное")
                font.capitalization: Font.MixedCase
                color: Theme.faint
                font.pixelSize: 10
            }
        }

        Mono {
            Layout.fillWidth: true
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            Layout.bottomMargin: 6
            visible: library.uploadStatus !== ""
            text: library.uploadStatus
            font.capitalization: Font.MixedCase
            color: library.uploading ? Theme.accentText : Theme.muted
        }

        FlatButton {
            Layout.fillWidth: true
            Layout.leftMargin: 8
            Layout.rightMargin: 8
            Layout.bottomMargin: 8
            glyph: Theme.iAdd
            text: library.uploading ? qsTr("Загрузка…") : qsTr("Загрузить музыку")
            enabledWhen: !library.uploading
            onClicked: fileDialog.open()
        }

        // --- the account ---
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 46
            color: "transparent"

            Rectangle {
                width: parent.width
                height: 1
                color: Theme.border
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 8
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: 24
                    Layout.preferredHeight: 24
                    color: Theme.accent

                    Mono {
                        anchors.centerIn: parent
                        text: (auth.displayName || auth.username || "?").charAt(0)
                        color: "white"
                        font.weight: Font.Bold
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0

                    Text {
                        Layout.fillWidth: true
                        text: auth.displayName || auth.username
                        color: Theme.text
                        font.family: Theme.sans
                        font.pixelSize: Theme.fontSmall
                        elide: Text.ElideRight
                    }
                    Mono {
                        Layout.fillWidth: true
                        visible: auth.isAdmin
                        text: qsTr("администратор")
                        font.pixelSize: 10
                        color: Theme.faint
                    }
                }

                IconButton {
                    glyph: Theme.iLogout
                    tooltip: qsTr("Выйти")
                    onClicked: auth.signOut()
                }
            }
        }
    }
}
