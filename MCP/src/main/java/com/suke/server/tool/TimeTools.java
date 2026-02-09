package com.suke.server.tool;

import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

/**
 * @author 自然醒
 * @version 1.0
 */
@Component
public class TimeTools {


    @Tool(description = "根据时区ID获取到当前时间")
    public String getTimeByZoneID(@ToolParam(description = "时区ID,比如Asia/Shanghai") String zoneID){
        ZoneId id = ZoneId.of(zoneID);
        ZonedDateTime zonedDateTime = ZonedDateTime.now(id);
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
        return zonedDateTime.format(formatter);
    }
}
