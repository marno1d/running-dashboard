package dev.rundashboard.app;
public final class ChartInteractionTest {
    static void expect(int actual,int expected){if(actual!=expected)throw new AssertionError(actual+" != "+expected);}
    static void check(boolean value){if(!value)throw new AssertionError();}
    public static void main(String[] args){
        expect(ChartInteraction.direction(3,4,8),0);
        expect(ChartInteraction.direction(8,8,8),0);
        // Vertical scrolling wins in either direction, even over a zoomed plot.
        expect(ChartInteraction.direction(5,24,8),-1);
        expect(ChartInteraction.direction(-5,-24,8),-1);
        expect(ChartInteraction.direction(16,16,8),-1);
        // Horizontal scrubs do not turn into page scrolls with minor jitter.
        expect(ChartInteraction.direction(24,5,8),1);
        expect(ChartInteraction.direction(-24,-5,8),1);
        check(ChartInteraction.adjacentWeeks(20000,20007));
        check(!ChartInteraction.adjacentWeeks(20000,20014));
        check(!ChartInteraction.adjacentWeeks(20000,20000));
        check(!ChartInteraction.adjacentWeeks(20007,20000));
        System.out.println("Chart scroll/pan intent and recovery missing-week gaps: OK");
    }
}
