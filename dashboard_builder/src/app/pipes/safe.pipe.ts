import { Pipe, PipeTransform, SecurityContext } from '@angular/core';
import { DomSanitizer } from '@angular/platform-browser';

@Pipe({name: 'safe', standalone: true})

export class SafePipe implements PipeTransform {

    constructor(private sanitizer: DomSanitizer) {}

    public transform(url: string | null) {
        const sanitizedUrl = this.sanitizer.sanitize(SecurityContext.URL, url);
        return sanitizedUrl ? this.sanitizer.bypassSecurityTrustResourceUrl(sanitizedUrl) : null;
    }
}
