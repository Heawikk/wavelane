import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import Wavelane

/*!
    Adding music: pick files, or a whole folder, on this device and they go up to the
    server one by one. The server reads the tags and covers and analyses the sound.
*/
Flickable {
    id: root

    property bool compact: false

    signal showConflicts()

    readonly property int margin: compact ? 14 : 24
    //! Android hands out a tree URI for a folder, which is not something to walk through.
    readonly property bool canPickFolder: Qt.platform.os !== "android" && Qt.platform.os !== "ios"

    function openFiles() { fileDialog.open() }
    function openFolder() { folderDialog.open() }

    contentWidth: width
    contentHeight: content.implicitHeight + 2 * margin
    boundsBehavior: Flickable.StopAtBounds
    clip: true

    ScrollBar.vertical: FlatScrollBar {}

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

    FolderDialog {
        id: folderDialog
        title: qsTr("Выберите папку с музыкой")
        onAccepted: library.uploadFolder(selectedFolder)
    }

    Column {
        id: content
        x: root.margin
        y: root.margin
        width: root.width - 2 * root.margin
        spacing: 18

        Mono {
            width: parent.width
            text: root.canPickFolder
                  ? qsTr("Файлы читаются с этого устройства и загружаются на сервер по одному. "
                         + "Папка загружается целиком, вместе с вложенными. Сервер сам прочитает "
                         + "теги и обложки и проанализирует звук.")
                  : qsTr("Файлы читаются с этого устройства и загружаются на сервер по одному. "
                         + "Сервер сам прочитает теги и обложки и проанализирует звук.")
            color: Theme.muted
            font.capitalization: Font.MixedCase
            font.letterSpacing: 0.2
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            lineHeight: 1.35
        }

        Flow {
            width: parent.width
            spacing: 10

            FlatButton {
                primary: true
                glyph: Theme.iAdd
                text: library.uploading ? qsTr("Загрузка…") : qsTr("Загрузить файлы")
                enabledWhen: !library.uploading
                onClicked: root.openFiles()
            }
            FlatButton {
                visible: root.canPickFolder
                glyph: Theme.iFolder
                text: qsTr("Загрузить папку")
                enabledWhen: !library.uploading
                onClicked: root.openFolder()
            }
            FlatButton {
                visible: library.conflicts.length > 0
                text: qsTr("Конфликты: %1").arg(library.conflicts.length)
                onClicked: root.showConflicts()
            }
        }

        Mono {
            width: parent.width
            visible: library.uploadStatus !== ""
            text: library.uploadStatus
            color: library.uploading ? Theme.accentText : Theme.muted
            font.capitalization: Font.MixedCase
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
        }

        // an import of a folder on the server itself, if one is running
        ImportBanner {
            width: parent.width
            onShowConflicts: root.showConflicts()
        }
    }
}
