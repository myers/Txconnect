HumanReadable = {
  filesize: function(bytes) {
    if (bytes == 0) {
      return '0';
    } else if (bytes < 1024) {
      return '<1 KiB';
    } else if (bytes < (1024 * 1024)) {
      return (bytes / 1024).toFixed(1) + ' KiB';
    } else if (bytes < (1024 * 1024 * 1024)) {
      return (bytes / 1024 / 1024).toFixed(1) + ' MiB';
    } else if (bytes < (1024 * 1024 * 1024 * 1024)) {
      return (bytes / 1024.0 / 1024.0 / 1024.0).toFixed(1) + ' GiB';
    } else {
      return (bytes / 1024.0 / 1024.0 / 1024.0 / 1024.0).toFixed(1) + ' TiB';
    }
  },
  
  time: function(seconds, parts) {
    if (seconds == Number.POSITIVE_INFINITY) { return ''; }
    if (parts === undefined) { parts = 2; }
    var ret = [];
    var days = Math.floor(seconds / (60 * 60 * 24));
    seconds = seconds % (60 * 60 * 24);
    if (days) { ret.push(days + 'd'); }
    var hours = Math.floor(seconds / (60 * 60));
    seconds = seconds % (60 * 60);
    if (ret.length || hours) { ret.push(hours + 'h') }
    var minutes = Math.floor(seconds / 60);
    seconds = seconds % 60
    if (ret.length || minutes) { ret.push(minutes + 'm'); }
    ret.push(seconds.toFixed(0) + 's');
    return ret.slice(0, parts).join(' ');
  },
  
  percent: function(numerator, denominator, places) {
    if (typeof(places) === 'undefined') { places = 0;  }
    return ((numerator/denominator) * 100).toFixed(places) + '%';
  },

  number: function(nStr) {
    nStr += '';
    var x = nStr.split('.');
    var x1 = x[0];
    var x2 = x.length > 1 ? '.' + x[1] : '';
    var rgx = /(\d+)(\d{3})/;
    while (rgx.test(x1)) {
      x1 = x1.replace(rgx, '$1' + ',' + '$2');
    }
    return x1 + x2;
  }
};
