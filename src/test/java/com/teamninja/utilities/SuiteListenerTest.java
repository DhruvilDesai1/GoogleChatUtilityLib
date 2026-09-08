package com.teamninja.utilities;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.testng.Assert;
import org.testng.annotations.Test;

public class SuiteListenerTest {

    @Test
    public void shortListIsUnchanged() {
        String formatted = SuiteListener.formatTestFiles(Arrays.asList("a.B", "c.D"));
        Assert.assertEquals(formatted, "- a.B\n- c.D\n");
    }

    @Test
    public void emptyListProducesEmptyString() {
        Assert.assertEquals(SuiteListener.formatTestFiles(new ArrayList<>()), "");
    }

    @Test
    public void longListIsCappedWithRemainderNote() {
        List<String> names = new ArrayList<>();
        for (int i = 0; i < 50; i++) {
            names.add("pkg.Test" + i);
        }
        String formatted = SuiteListener.formatTestFiles(names);
        Assert.assertEquals(countOccurrences(formatted, "- pkg.Test"), 20);
        Assert.assertTrue(formatted.contains("...and 30 more"),
                "expected a remainder note, got: " + formatted);
    }

    @Test
    public void listAtExactlyTheCapHasNoRemainderNote() {
        List<String> names = new ArrayList<>();
        for (int i = 0; i < 20; i++) {
            names.add("pkg.Test" + i);
        }
        Assert.assertFalse(SuiteListener.formatTestFiles(names).contains("more"));
    }

    private static int countOccurrences(String haystack, String needle) {
        int count = 0;
        int index = haystack.indexOf(needle);
        while (index >= 0) {
            count++;
            index = haystack.indexOf(needle, index + needle.length());
        }
        return count;
    }
}
