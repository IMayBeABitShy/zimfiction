// This script is used to configure a chart.js chart showing data about a list of stories over time


async function on_load(event) {
    // called when everything was loaded
    // 1. fetch dataset
    console.log("Fetching chart dataset...")
    var response = await fetch("storyupdates.json");
    if (!response.ok) {
        // file not found
        console.log("HTTP error " + response.status);
        return false;
    }
    try {
        var dataset = await response.json();
    } catch {
        // invalid json
        console.log("Error reading timeline data file!");
        return false;
    }
    console.log("Successfully retrieved search header.");
    // 2. init chart
    new Chart(
        document.getElementById("storyupdatechart"),
        {
            type: "line",
            data: {
                labels: dataset.months,
                datasets: [
                    {
                        label: "Stories published",
                        data: dataset.published,
                        borderColor: "red",
                        fill: false
                    },
                    {
                        label: "Last stories updates",
                        data: dataset.updated,
                        borderColor: "blue",
                        fill: false
                    }
                ]
            },
            options: {
                legend: {
                    display: true
                }
            }
        }
    );
}

function main() {
    // the main function
    window.addEventListener("load", on_load)
}

main();
