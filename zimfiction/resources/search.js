// Search script for zimfiction

// globals
const ID_STORYDIV = "storylistdiv";
const ID_STATUSDIV = "statusdiv";
const STORIES_PER_PAGE = 20;


// the search
class ZimfictionSearch {
    // The search class
    constructor() {
        // the default constructor.
        this.set_status("Initializing");
    }

    async start() {
        // start the search
        // this will load the header files, install handlers, ...
        await this.fetch_header();
    }

    set_status(status) {
        // set the status message
        console.log("status: ", status);
        var status_html = `<P>${status}</P>`
        this.replace_html_content(ID_STATUSDIV, status_html);
    }

    replace_html_content(id, new_content) {
        // replace the content of the HTML element with the specified ID with new_content
        var element = document.getElementById(id);
        if (element === null) {
            console.log("Warning: element with ID ", id, " not found!")
            console.log("New content would be:");
            console.log(new_content)
        } else {
            element.innerHTML = new_content;
        }
    }

// run logic
async function main() {
    // the main function
    var search = new ZimfictionSearch();
    await search.start();
}

main();
