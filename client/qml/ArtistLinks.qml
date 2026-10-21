import QtQuick
import Wavelane

/*!
    The names of a track's artists, each one a link to that artist's page: "A, B feat. C".

    Without credits (a track the server described in the old way) the plain text shows
    instead. A click on a name opens the artist; a click anywhere else on the text is passed on to
    whatever lies underneath, such as the row the text is in.
*/
Text {
    id: root

    //! Maps with "id", "name" and "role" ("main" or "featured"), as a track carries them.
    property var artists: []
    //! Shown when there are no credits.
    property string fallback: ""

    readonly property bool linked: artists !== undefined && artists !== null && artists.length > 0

    function esc(value) {
        return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }

    function anchor(artist) {
        const name = esc(artist.name)
        return '<a href="' + artist.id + '">' + (artist.id === root.hoveredLink ? "<u>" + name + "</u>" : name) + "</a>"
    }

    function markup() {
        const main = []
        const featured = []
        for (let i = 0; i < artists.length; ++i)
            (artists[i].role === "featured" ? featured : main).push(anchor(artists[i]))
        let text = main.join(", ")
        if (featured.length > 0)
            text += (text ? " feat. " : "feat. ") + featured.join(", ")
        return text
    }

    function nameOf(id) {
        for (let i = 0; i < artists.length; ++i)
            if (artists[i].id === id)
                return artists[i].name
        return ""
    }

    textFormat: linked ? Text.StyledText : Text.PlainText
    text: linked ? markup() : fallback
    linkColor: color
    font.family: Theme.sans
    elide: Text.ElideRight

    onLinkActivated: function(id) { library.showArtist(id, nameOf(id)) }

    HoverHandler {
        cursorShape: root.hoveredLink !== "" ? Qt.PointingHandCursor : Qt.ArrowCursor
    }
}
