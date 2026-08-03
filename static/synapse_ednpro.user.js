// ==UserScript==
// @name        Synapse EDNpro
// @namespace   http://tampermonkey.net/
// @version     1.0
// @description Auto search item
// @author      Synapse
// @match       https://ednpro.app/*
// @grant       none
// ==UserScript==

(function() {
    var params = new URLSearchParams(window.location.search);
    var itemNum = params.get('item') || params.get('search');
    if (!itemNum) return;

    var cleanNum = itemNum.replace('ITEM', '').trim();
    var hasClicked = false;

    function doSearchAndOpen() {
        var input = document.querySelector('input');
        if (input) {
            if (input.value !== cleanNum && input.value !== 'ITEM ' + cleanNum) {
                input.value = cleanNum;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }

            setTimeout(function() {
                if (hasClicked) return;
                var allDivs = document.querySelectorAll('div, span, p');
                for (var i = 0; i < allDivs.length; i++) {
                    var txt = (allDivs[i].textContent || '').trim();
                    if (txt === '#' + cleanNum || txt === '# ' + cleanNum) {
                        allDivs[i].click();
                        if (allDivs[i].parentElement) allDivs[i].parentElement.click();
                        hasClicked = true;
                        break;
                    }
                }
            }, 500);
        } else {
            setTimeout(doSearchAndOpen, 300);
        }
    }

    setTimeout(doSearchAndOpen, 500);
})();
