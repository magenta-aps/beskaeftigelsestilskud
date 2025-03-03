const renderGraph = function (selector, data, yearlyIncome, yearlyBenefit) {
    const graph = $(selector);

    if (yearlyIncome > data[data.length - 1][0]) {
        // result is greater than our current max point in the graph
        data = [...data, [yearlyIncome, 0]];  // Clone array
    }

    let chartData = {
        "chart": {
            "nonce": "{{ request.csp_nonce }}",
            "type": "line",
            "toolbar": {"show": false},
            "animations": {"enabled": false},
            "selection": {"enabled": false},
            "fontFamily": "Figtree Normal, Trebuchet MS, Helvetica, sans-serif",
            "height": "100%"
        },
        "tooltip": {"enabled": false},
        "colors": ["#000000"],
        "series": [{
            "name": "Suila",
            "data": data,
        }],
        "legend": {
            "fontSize": "1.5rem"
        },
        "xaxis": {
            "type": "numeric",
            "title": {
                "text": gettext("Årsindkomst i kr."),
                "style": {"fontSize": "1.5rem"},
            },
            "labels": {"style": {"fontSize": "1rem"}},
        },
        "yaxis": {
            "title": {
                "text": gettext("Suila-tapit i kr."),
                "style": {"fontSize": "1.5rem"},
            },
            "labels": {"style": {"fontSize": "1rem"}},
        },
    };

    if (!isNaN(yearlyIncome) && !isNaN(yearlyBenefit)) {
        chartData["annotations"] = {
            "points": [{
                "x": yearlyIncome,
                "y": yearlyBenefit,
                "marker": {
                    "size": 4,
                },
                "label": {
                    "text": [
                        gettext("Beregnet Suila for hele året: ") + yearlyBenefit,
                    ],
                    "style": {
                        "background": "#fff",
                        "color": "#333",
                        "fontSize": "1.5rem",
                    }
                }
            }]
        }
    }

    const chart = new ApexCharts(graph.get(0), chartData);
    chart.render();
}
