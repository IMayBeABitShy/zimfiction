// Search script for zimfiction

// globals
const TO_ROOT = "../../..";
const ID_STORY_DIV = "storylistdiv";
const ID_STATUS_DIV = "statusdiv";
const ID_SEARCH_BUTTON = "search_button";
const ID_SORT_SELECT = "search_sort_select";
const ID_TOGGLE_SEARCH_INPUT_BUTTON = "toggle_search_input_button";
const ID_PAGE_BUTTONS_DIV = "page_buttons";
const FIELDS = ["publisher", "language", "status", "categories", "warnings", "characters", "relationships", "tags", "rating"];
const RANGE_FIELDS = ["words", "chapters", "score", "category_count"];
const STORIES_PER_PAGE = 20;
const MAX_AUTOCOMPLETE = 10;


// preview template
const PREVIEW_TEMPLATE = `
<DIV class="story_summary">
    <DIV class="summary_title">
        <A href="${TO_ROOT}/story/{publisher}/{story_id}/" class="summary_title_link">{title}</A> by <A class="summary_author_link" href="${TO_ROOT}/author/{publisher}/{normalized_author}/">{author}</A>
        <P class="story_updated_text">{updated}</P>
        <DIV class="short_categories">
            {categorylist}
        </DIV>
    </DIV>
    <DIV class="short_tags">
        {taglist}
    </DIV>
    <BR>
    <DIV class="summary_text">
        {summary}
    </DIV>
    <DIV class="summary_footer">
        <P>
            {serieslist}
            <B>Language:</B> {language} <B>Status:</B> {status} <B>Rating: </B> {rating} <B>Words:</B> {total_words} <B>Chapters:</B> {chapters} <B>Score:</B> {score}
        </P>
    </DIV>
</DIV>
`


// helper functions
function obj_has_key(object, key) {
    // return true if object has the specified key
    if (Object.hasOwn === undefined) {
        return object.hasOwnProperty(key);
    }
    return Object.hasOwn(object, key);
}


function escapeHtml(unsafe) {
    // escape html
    // source: https://stackoverflow.com/a/6234804
    return unsafe
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
         // .replace(/'/g, "_");
 }


function normalize_tag(tag) {
    // normalize a tag for usage in urls
    // IMPORTANT: be sure this matches the behavior of the python function
    return tag.replaceAll(" ", "+").replaceAll("/", "__");
}


// the search
class ZimfictionSearch {
    // The search class
    constructor() {
        // the default constructor.
        this.set_status("Initializing...");
        this.header = null;
        this.results = [];
        this.field2tags = {};  // field name -> possible tags for this field
        this.amounts = null;  // mapping of tag_id -> number of occurences
    }

    async start() {
        // start the search
        // this will load the header files, install handlers, ...
        this.set_search_enabled(false);
        this.install_handlers();
        var search_available = await this.fetch_header();
        if (!search_available) {
            // search not available, exiting
            return;
        }
        this.init_autocomplete_values();
        this.install_autocomplete();
        this.set_search_enabled(true);
        this.set_status("Search is ready.");
    }

    set_status(status) {
        // set the status message
        console.log("status: ", status);
        var status_html = `<P>${status}</P>`
        this.replace_html_content(ID_STATUS_DIV, status_html);
    }

    async fetch_header() {
        // fetch the header file
        // return true if the search is available, false otherwise
        this.set_status("Fetching header...");
        var response = await fetch("search_header.json");
        if (!response.ok) {
            // file not found, this can happen if there's no search metadata for this tag/category/...
            console.log("HTTP error " + response.status);
            this.set_status("Search is not available");
            return false;
        }
        try {
            var json = await response.json();
        } catch {
            // invalid json
            console.log("Error reading header file!");
            this.set_status("Error loading search data!");
            return false;
        }
        console.log("Successfully retrieved search header.");
        this.header = json;
        this.amounts = this.header["amounts"];
        return true;
    }

    async fetch_preview_data(publisher, id) {
        // fetch the preview data for a specific story
        console.log("Fetching Preview for..." + publisher + "/" + id);
        var target = `${TO_ROOT}/story/${publisher}/${id}/preview.json`
        var response = await fetch(target);
        if (!response.ok) {
            console.log("HTTP error " + response.status);
            this.set_status("Error loading preview");
            return null;
        }
        try {
            var json = await response.json();
        } catch {
            // invalid json
            console.log("Error reading preview!");
            this.set_status("Error loading preview file '" + id + "'!");
            return null;
        }
        return json;
    }

    get_possible_values_for(field) {
        // return an array containing all known values for a field (e.g. languages)
        if (!obj_has_key(this.header["tag_ids"], field)) {
            // no values for this tag
            console.log("Warning: field '" + field + "' not known!");
            return [];
        }
        return Object.keys(this.header["tag_ids"][field]);
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

    async on_search(event) {
        // called when the search button was clicked
        var element = event.target;
        var search = element.search_object;
        await search.do_search();
    }

    async do_search() {
        // perform a search
        // prevent further search
        this.set_search_enabled(false);
        // get input parameters
        var criterias = this.get_search_criterias();
        var sort_order = this.get_sort();
        var range_criterias = this.get_range_criterias();
        // check if range criterias is invalid
        if (range_criterias === null) {
            this.set_status("Invalid range values!");
            this.set_search_enabled(true);
            return;
        }
        // resolve
        var resolved = this.resolve_criterias(criterias);
        if (resolved === null) {
            // invalid search
            this.set_status("Invalid search parameters!");
            this.set_search_enabled(true);
            return;
        }
        // clear old search
        this.results = [];
        this.clear_results();
        // find matches
        this.results = await this.find_all_matches(resolved, range_criterias);
        if (this.results === null) {
            // search failed
            return;
        }
        this.apply_sort(sort_order);
        this.update_autocomplete_values();
        this.set_status("" + this.results.length + " Results");
        this.display_result_page(1);
        // finish
        this.set_search_enabled(true);
    }

    set_search_enabled(enabled) {
        // set wether the search is enabled or not
        var search_button = document.getElementById(ID_SEARCH_BUTTON);
        search_button.disabled = !enabled;
    }

    install_handlers() {
        // install the various UI event handlers
        // 1. the search collapsible
        document.getElementById(ID_TOGGLE_SEARCH_INPUT_BUTTON).addEventListener(
            "click",
            function() {
                this.classList.toggle("active");
                var content = this.nextElementSibling;
                if (content.style.display == "block") {
                    content.style.display = "none";
                } else {
                    content.style.display = "block";
                }
            }
        );
        // 2. the range fields
        for (const fieldname of RANGE_FIELDS) {
            for (const limiter of ["min", "max"]) {
                var element_id = `search_input_${fieldname }_${ limiter }`;
                var element = document.getElementById(element_id);
                element.addEventListener(
                    "input",
                    function(event) {
                        var inp = event.target;
                        var value = inp.value;
                        if (value.length > 0 && isNaN(value)) {
                            // not a valid number
                            inp.style.border = "thick solid red";
                        } else {
                            inp.style.border = "";
                        }
                    }
                );
            }
        }
        // 3. the search button
        var search_button = document.getElementById(ID_SEARCH_BUTTON);
        search_button.search_object = this;
        search_button.addEventListener(
            "click",
            this.on_search,
        );
    }

    install_autocomplete() {
        // install the autocomplete for the input
        for (const field of FIELDS) {
            var elementid = "search_input_" + field;
            var element = document.getElementById(elementid);
            element.search_object = this;  // so we can handle events here
            var values = this.field2tags[field];
            autocomplete(element, values);
        }
    }

    init_autocomplete_values() {
        // populate this.field2tags with the autocomplete values
        this.field2tags = {};
        for (const field of FIELDS) {
            this.field2tags[field] = this.get_possible_values_for(field);
        }
        this.update_autocomplete_values();
    }

    update_autocomplete_values() {
        // update the autocomplete values (e.g. by ordering them by current occurences)
        for (const field of FIELDS) {
            this.field2tags[field].sort((a, b, fieldname=field) => this.autocomplete_sort_function(fieldname, a, b));
        }
    }

    autocomplete_sort_function(fieldname, a, b) {
        // a sort function for ordering the fields in an autocomplete field
        // by occurences
        return (this.get_occurences_of(fieldname, b) - this.get_occurences_of(fieldname, a))
    }

    on_autocomplete(inp, value) {
        // called when an input value was autocompleted
        // in our case, this means that a new search criteria was added
        var id = inp.id;
        var field = id.replace("search_input_", "");
        var sanitized = escapeHtml(value);
        // add a new criteria to the list
        var ul_id = `search_field_list_${field}`;
        var ul = document.getElementById(ul_id);
        var li_id = `search_criteria_${field}_${sanitized}`;
        var unescaped_li_id = `search_criteria_${field}_${value}`;
        if (!(document.getElementById(li_id) === null)) {
            // this value has already been registered, do nothing
            return;
        }
        var inc_button_id = `search_include_button_${field}_${sanitized}`;
        var unescaped_inc_button_id = `search_include_button_${field}_${value}`;
        var impl_button_id = `search_implied_button_${field}_${sanitized}`;
        var unescaped_impl_button_id = `search_implied_button_${field}_${value}`;
        var remove_button_id = `search_remove_button_${field}_${sanitized}`;
        var unescaped_remove_button_id = `search_remove_button_${field}_${value}`;
        var li_html = `<LI class="search_criteria" id="${li_id}">${sanitized}<DIV class="criteria_buttons"><BUTTON id="${inc_button_id}" class="include_button" title="Whether to find stories with or without this tag">Include</BUTTON><BUTTON id="${impl_button_id}" class="implied_button" title="Whether to only search explicitly mentioned tags or also implied oens">I</BUTTON><BUTTON id="${remove_button_id}" class="remove_button" title="Remove this search criteria">X</BUTTON></DIV></LI>`;
        ul.insertAdjacentHTML("beforeend", li_html);
        // wire up the elements
        var li = document.getElementById(unescaped_li_id);
        var inc_button = document.getElementById(unescaped_inc_button_id);
        var impl_button = document.getElementById(unescaped_impl_button_id);
        var remove_button = document.getElementById(unescaped_remove_button_id);
        li.criteria_field = field;
        li.criteria_value = value;
        li.criteria_include = true;
        li.criteria_implied = true;
        inc_button.addEventListener("click", this.on_include_button_click);
        inc_button.target_id = unescaped_li_id;
        impl_button.addEventListener("click", this.on_implied_button_click);
        impl_button.target_id = unescaped_li_id;
        remove_button.addEventListener("click", this.on_remove_button_click);
        remove_button.target_id = unescaped_li_id;
    }

    on_include_button_click(event) {
        // called when the include/exclude toggle button was clicked
        var element = event.target;
        var target = document.getElementById(element.target_id);
        var cur_state = target.criteria_include;
        if (cur_state) {
            element.innerHTML = "Exclude";
            target.criteria_include = false;
        } else {
            element.innerHTML = "Include";
            target.criteria_include = true;
        }
        event.preventDefault();
    }

    on_implied_button_click(event) {
        // called when the implied/explicit toggle button was clicked
        var element = event.target;
        var target = document.getElementById(element.target_id);
        var cur_state = target.criteria_implied;
        if (cur_state) {
            element.innerHTML = "E";
            target.criteria_implied = false;
        } else {
            element.innerHTML = "I";
            target.criteria_implied = true;
        }
        event.preventDefault();
    }

    on_remove_button_click(event) {
        // called when the remove button was clicked
        var element = event.target;
        var target_id = element.target_id;
        var target = document.getElementById(target_id);
        target.parentElement.removeChild(target);
        event.preventDefault();
    }

    get_search_criterias() {
        // return a list of tuples of (field, value, include, implied) of all search criterias
        var criterias = [];
        var elements = document.getElementsByClassName("search_criteria");
        for (const element of elements) {
            var criteria = [element.criteria_field, element.criteria_value, element.criteria_include, element.criteria_implied];
            criterias.push(criteria);
        }
        return criterias;
    }

    get_range_criterias() {
        // return a list of tuples of (field, min, max) of all range criterias
        // returns none on invalid input
        var criterias = [];
        for (const fieldname of RANGE_FIELDS) {
            var cur = [fieldname];
            var has_any = false;
            for (const limiter of ["min", "max"]) {
                var element_id = `search_input_${fieldname }_${ limiter }`;
                var element = document.getElementById(element_id);
                var value = element.value;
                if (value.length == 0) {
                    // no limit
                    if (limiter == "min") {
                        cur.push(Number.NEGATIVE_INFINITY);
                    } else {
                        cur.push(Number.POSITIVE_INFINITY);
                    }
                } else if (isNaN(value)) {
                    // invalid input
                    return null;
                } else {
                    cur.push(parseInt(value));
                    has_any = true;
                }
            }
            // only add range criteria if at least on limit was specified
            if (has_any) {
                criterias.push(cur);
            }
        }
        return criterias;
    }

    get_sort() {
        // return the currently selected sort
        var select = document.getElementById(ID_SORT_SELECT);
        return select.value;
    }

    resolve_criterias(criterias) {
        // resolve a list of criterias to tag ids
        // criterias should be a list of [[field, value, include, implied], ...]
        // returns a list of [[tag_id, include, implied], ...], sorted.
        // returns null if search is invalid

        // resolve tag ids
        var resolved = [];
        var all_tag_ids = this.header["tag_ids"];
        for (const criteria of criterias) {
            var field = criteria[0];
            var value = criteria[1];
            var include = criteria[2];
            var implied = criteria[3];
            // check if criteria is valid
            if (!obj_has_key(all_tag_ids, field)) {
                console.log("Error: No such field: '" + field + "'!");
                return null;
            }
            if (!obj_has_key(all_tag_ids[field], value)) {
                console.log("Error: No such value '" + value + "' for field '" + field + "'!");
                return null;
            }
            // resolve
            var tag_id = all_tag_ids[field][value];
            resolved.push([tag_id, include, implied]);
        }
        // sort by first element
        resolved.sort((a, b) => (a[0] - b[0]));
        return resolved;
    }

    async find_all_matches(resolved_criterias, range_criterias) {
        // return a list of all stories that match the specified criterias
        // expects the result of resolve_criterias() as an argument
        var results = [];
        var amounts = {};
        // the stories are grouped together in multiple files
        // iterate over each file
        var cur_file = 0;
        var num_files = this.header["num_pages"];
        while (cur_file < num_files) {
            var cfp = cur_file + 1;
            this.set_status(`Searching (${cfp}/${num_files})...`);
            var filename = `search_content_${cur_file}.json`;
            var response = await fetch(filename);
            if (!response.ok) {
                // file not found, this can happen if there's no search metadata for this tag/category/...
                console.log("HTTP error " + response.status);
                this.set_status("Failed to retrieve search body file " + filename + "!");
                return null;
            }
            try {
                var body = await response.json();
            } catch {
                // invalid json
                console.log("Error reading file: '" + filename + "'!");
                this.set_status("Error reading file: '" + filename + "'!");
                return null;
            }

            // search through all stories in this body file
            for (const story of body) {
                if (this.does_story_match_criterias(story, resolved_criterias, range_criterias)) {
                    results.push(story);
                    // update amounts
                    for (const tag_id of story["tags"]) {
                        if (obj_has_key(amounts, tag_id)) {
                            amounts[tag_id] = amounts[tag_id] + 1;
                        } else {
                            amounts[tag_id] = 1;
                        }
                    }
                }
            }

            cur_file += 1;
        }
        this.amounts = amounts;
        return results;
    }

    does_story_match_criterias(story, resolved_criterias, range_criterias) {
        // check if a story matches the resolved criterias

        // tag checks
        // we could use indexes and sort order to check this more efficiently
        // but for now, lets just use a simple loop
        var tag_ids = story["tags"]
        var implied_tag_ids = story["implied_tags"];
        for (const criteria of resolved_criterias) {
            var tag_id = criteria[0];
            var include = criteria[1];
            var implied = criteria[2];
            if (tag_ids.includes(tag_id)){
                if (!include) {
                    // has tag but we filter by exclude
                    return false;
                }
            } else if (implied && implied_tag_ids.includes(tag_id)) {
                // story does not explicitly have tags
                // but we should search implied tags and an implied tag has it
                if (!include) {
                    // tag is implied but we filter by exclude
                    return false;
                }
            } else if (include) {
                // does not have tag but is required
                return false;
            }
        }
        // range criteria checks
        for (const range_criteria of range_criterias) {
            var field = range_criteria[0];
            var value = story[field];
            if (value < range_criteria[1] || value > range_criteria[2]) {
                // outside range
                return false;
            }
        }
        // all criterias fulfilled, story matches
        return true;
    }

    clear_results() {
        // clear the result list
        this.replace_html_content(ID_STORY_DIV, "");
    }

    display_result_page(pagenum) {
        // show the specified page (1-based index) of the search results
        this.clear_results();
        var start_i = (pagenum - 1) * STORIES_PER_PAGE;
        var end_i = start_i + STORIES_PER_PAGE;
        if (end_i > this.results.length) {
            end_i = this.results.length;
        }
        var to_display = this.results.slice(start_i, end_i);
        var story_div = document.getElementById(ID_STORY_DIV);
        for (const story of to_display) {
            // display a placeholder
            var publisher = story["publisher"];
            var story_id = story["id"];
            var preview_id = `preview-${publisher}-${story_id}`;
            var placeholder = `<DIV class="story_list_page_item" id="${preview_id}">Loading preview, please wait...</DIV>`;
            story_div.insertAdjacentHTML("beforeend", placeholder);
            var preview_file_name = `${TO_ROOT}/story/${publisher}/${story_id}/preview.json`;
            fetch(preview_file_name).then(x => x.json()).then(x => this.on_preview_received(x));
        }
        // set page buttons
        var button_html = "";
        var pagebutton_numbers = [];
        var numpages = Math.ceil(this.results.length / STORIES_PER_PAGE);
        // first page button
        if (pagenum > 3) {
            button_html += this.render_pagebutton(1);
            pagebutton_numbers.push(1);
        }
        // skip between first and surroundings
        if (pagenum > 4) {
            button_html += this.render_pagebuttonskip();
        }
        // surroundings
        var i = Math.max(1, pagenum-2);
        while (i < Math.min(pagenum+3, numpages+1)) {
            if (i == pagenum) {
                button_html += this.render_curpagebutton(i);
            } else {
                button_html += this.render_pagebutton(i);
            }
            pagebutton_numbers.push(i);
            i += 1;
        }
        // skip between suroundings and end
        if (pagenum + 3 < numpages) {
            button_html += this.render_pagebuttonskip();
        }
        // last page button
        if (pagenum + 2 < numpages) {
            button_html += this.render_pagebutton(numpages);
            pagebutton_numbers.push(numpages);
        }
        // install and wire up buttons
        this.replace_html_content(ID_PAGE_BUTTONS_DIV, button_html);
        for (const buttonnumber of pagebutton_numbers) {
            var element = document.getElementById("page-button-" + buttonnumber);
            element.onclick = (() => {this.display_result_page(buttonnumber)});
        }
    }

    render_pagebutton(pagenum) {
        // render a single pagebutton
        var html = `
        <DIV class="page_button">
            <P><A class="page_button_link" id="page-button-${pagenum}">${pagenum}</A></P>
        </DIV>
        `
        return html;
    }

    render_curpagebutton(pagenum) {
        // render the current pagebutton
        var html = `
        <DIV class="page_button">
            <P><A class="page_button_link cur_page_button_link" id="page-button-${pagenum}">${pagenum}</A></P>
        </DIV>
        `
        return html;
    }

    render_pagebuttonskip() {
        // render a single skip pagebutton
        var html = `
        <DIV class="page_button">
            <P>...</P>
        </DIV>
        `
        return html;
    }

    on_preview_received(json) {
        // called when the preview data was received
        var publisher = json["publisher"];
        var story_id = json["id"];
        var preview_id = `preview-${publisher}-${story_id}`;
        var formated = this.format_preview(json);
        this.replace_html_content(preview_id, formated);
    }

    format_preview(preview) {
        // fill the preview template with the provided preview data
        var publisher = preview["publisher"];
        var categorylist = "";
        var first = true;
        for (const category of preview["categories"]) {
            if (!first) {
                categorylist += ", ";
            } else {
                first = false;
            }
            var normalized_category = normalize_tag(category);
            var escaped_category = escapeHtml(category);
            categorylist += `<A class="categorylink" href="${TO_ROOT}/category/${publisher}/${normalized_category}/">${escaped_category}</A>`
        }
        var taglist = "";
        first = true;
        for (const taginfo of preview["tags"]) {
            var tagtype = taginfo[0];
            var tagname = taginfo[1];
            if (!first) {
                taglist += ", ";
            } else {
                first = false;
            }
            var normalized_tag = normalize_tag(tagname);
            var escaped_tag = escapeHtml(tagname);
            taglist += `<A class="taglink taglink-${tagtype}" href="${TO_ROOT}/tag/${tagtype}/${normalized_tag}/">${escaped_tag}</A>`
        }
        var serieslist = "";
        for (const series of preview["series"]) {
            var seriesname = series[0];
            var normalized_seriesname = normalize_tag(seriesname);
            var escaped_seriesname = escapeHtml(seriesname);
            var seriesindex = series[1];
            serieslist += `<B>Part</B> ${seriesindex} <B>of</B> <A class="serieslink" href="${TO_ROOT}/series/${publisher}/${normalized_seriesname}/">${escaped_seriesname} </A>`;
        }
        var args = [
            ["publisher", preview["publisher"]],
            ["story_id", "" + preview["id"]],
            ["title", preview["title"]],
            ["author", preview["author"]],
            ["normalized_author", normalize_tag(preview["author"])],
            ["updated", preview["updated"]],
            ["summary", preview["summary"]],
            ["language", preview["language"]],
            ["status", preview["status"]],
            ["total_words", preview["words"]],
            ["chapters", preview["chapters"]],
            ["score", preview["score"]],
            ["rating", preview["rating"]],
            ["categorylist", categorylist],
            ["taglist", taglist],
            ["serieslist", serieslist],
        ];
        // fill in the template
        var template = PREVIEW_TEMPLATE;
        for (const replacement_info of args) {
            var key = replacement_info[0];
            var value = replacement_info[1];
            template = template.replaceAll("{" + key + "}", value);
        }
        return template;
    }

    apply_sort(sort_order) {
        // order this.results by the specified sort order
        if (sort_order == "updated") {
            this.results.sort((a, b) => {
                if (a["updated"] < b["updated"]) {
                    return 1;
                }
                if (a["updated"] > b["updated"]) {
                    return -1;
                }
                return 0;
            });
        } else if (sort_order == "words") {
            this.results.sort((a, b) => (b["words"] - a["words"]));
        } else if (sort_order == "chapters") {
            this.results.sort((a, b) => (b["chapters"] - a["chapters"]));
        } else if (sort_order == "score") {
            this.results.sort((a, b) => (b["score"] - a["score"]));
        } else if (sort_order == "random") {
            this.random_shuffle(this.results);
        }
    }

    random_shuffle(a) {
        // randomly shuffles an array using the fisher-yates algorithm
        for (let i = a.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            const t = a[i];
            a[i] = a[j];
            a[j] = t;
        }
    }

    get_occurences_of(field, name) {
        // return the number of occurences a tag has in the current result set
        // if there are no results, return the general number of occurences
        var tag_id = this.header["tag_ids"][field][name];
        if (this.results.length > 0) {
            // get amount from result set
            if (obj_has_key(this.amounts, tag_id)) {
                return this.amounts[tag_id];
            } else {
                return 0;
            }
        } else {
            // get base amount
            return this.header["amounts"][tag_id];
        }
    }

    get_occurences_for_autocomplete(inp, value) {
        // return the number of occurences for a specific autocomplete value
        var id = inp.id;
        var field = id.replace("search_input_", "");
        return this.get_occurences_of(field, value);
    }
}

// autocomplete logic
// modified version taken from https://www.w3schools.com/howto/howto_js_autocomplete.asp

function autocomplete(inp, arr) {
    // the autocomplete function takes two arguments:
    // the text field element and an array of possible autocompleted values:
    var currentFocus;
    /*execute a function when someone writes in the text field:*/
    inp.addEventListener("input", function(e) {
        var a, b, i, val = this.value;
        /*close any already open lists of autocompleted values*/
        closeAllLists();
        if (!val) { return false;}
        currentFocus = -1;
        /*create a DIV element that will contain the items (values):*/
        a = document.createElement("DIV");
        a.setAttribute("id", this.id + "autocomplete-list");
        a.setAttribute("class", "autocomplete-items");
        /*append the DIV element as a child of the autocomplete container:*/
        this.parentNode.appendChild(a);
        var previews_created = 0;
        /*for each item in the array...*/
        for (i = 0; i < arr.length; i++) {
            /*check if the item starts with the same letters as the text field value:*/
            if (arr[i].substr(0, val.length).toUpperCase() == val.toUpperCase() && (previews_created < MAX_AUTOCOMPLETE)) {
                /*create a DIV element for each matching element:*/
                b = document.createElement("DIV");
               /*make the matching letters bold:*/
               b.innerHTML = "<strong>" + arr[i].substr(0, val.length) + "</strong>";
               b.innerHTML += arr[i].substr(val.length) + " (" + inp.search_object.get_occurences_for_autocomplete(inp, arr[i]) + ")";
               /*insert a input field that will hold the current array item's value:*/
               // b.innerHTML += "<input type='hidden' value='" + arr[i] + "'>";
               b.autocomplete_value = arr[i];
               /*execute a function when someone clicks on the item value (DIV element):*/
               b.addEventListener("click", function(e) {
                   /*insert the value for the autocomplete text field:*/
                   // var value = this.getElementsByTagName("input")[0].value;
                   var value = this.autocomplete_value;
                   inp.value = "";
                   inp.search_object.on_autocomplete(inp, value);
                   /*close the list of autocompleted values,
                   (or any other open lists of autocompleted values:*/
                   closeAllLists();
               });
               a.appendChild(b);
               previews_created += 1;
            }
        }
    });
    /*execute a function presses a key on the keyboard:*/
    inp.addEventListener("keydown", function(e) {
        var x = document.getElementById(this.id + "autocomplete-list");
        if (x) x = x.getElementsByTagName("div");
        if (e.keyCode == 40) {
            /*If the arrow DOWN key is pressed,
            increase the currentFocus variable:*/
            currentFocus++;
            /*and and make the current item more visible:*/
            addActive(x);
        } else if (e.keyCode == 38) { //up
            /*If the arrow UP key is pressed,
            decrease the currentFocus variable:*/
            currentFocus--;
            /*and and make the current item more visible:*/
            addActive(x);
        } else if (e.keyCode == 13) {
            /*If the ENTER key is pressed, prevent the form from being submitted,*/
            e.preventDefault();
            if (currentFocus > -1) {
                /*and simulate a click on the "active" item:*/
               if (x) x[currentFocus].click();
            }
        }
    });
    function addActive(x) {
        /*a function to classify an item as "active":*/
        if (!x) return false;
        /*start by removing the "active" class on all items:*/
        removeActive(x);
        if (currentFocus >= x.length) currentFocus = 0;
        if (currentFocus < 0) currentFocus = (x.length - 1);
        /*add class "autocomplete-active":*/
        x[currentFocus].classList.add("autocomplete-active");
    }
    function removeActive(x) {
        /*a function to remove the "active" class from all autocomplete items:*/
        for (var i = 0; i < x.length; i++) {
            x[i].classList.remove("autocomplete-active");
        }
    }
    function closeAllLists(elmnt) {
        /*close all autocomplete lists in the document,
        except the one passed as an argument:*/
        var x = document.getElementsByClassName("autocomplete-items");
        for (var i = 0; i < x.length; i++) {
            if (elmnt != x[i] && elmnt != inp) {
                x[i].parentNode.removeChild(x[i]);
            }
        }
    }
    /*execute a function when someone clicks in the document:*/
    document.addEventListener("click", function (e) {
        closeAllLists(e.target);
    });
}

// run logic

async function on_load(event) {
    // called when everything was loaded
    var search = new ZimfictionSearch();
    await search.start();
}

function main() {
    // the main function
    window.addEventListener("load", on_load)
}

main();
